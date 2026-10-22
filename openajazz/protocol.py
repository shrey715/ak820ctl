"""Wire protocol for the AJAZZ AK820 Max Plus, reconstructed from DeviceDriver.exe v1.0.4.6.

Every command is a 64-byte HID *output* report (report ID 0) on the vendor
collection with usage page 0xFF02 / usage 0x02:

    AA 55 CC 33 <cmd> <args...> 00...

See PROTOCOL.md for the evidence (function addresses) behind each command.
"""

from __future__ import annotations

import glob
import os
import select
import time
from dataclasses import dataclass

from . import keys

VENDOR_ID = 0x1A2C
PRODUCTS = {0xA036: "USB (wired)", 0x8FFF: "2.4G dongle"}
MAGIC = bytes([0xAA, 0x55, 0xCC, 0x33])
REPORT_LEN = 64
CHUNK = 54  # payload bytes per bulk packet (64 - 4 magic - 1 cmd - 5 spare)

CMD_KEY_CHUNK0 = 0x00  # 0x00..0x02: macro / combo key assignment, 3 chunks
CMD_REMAP = 0x04
CMD_LIGHT = 0x07
CMD_FACTORY_RESET = 0x08
CMD_STREAM_BEGIN = 0x09
CMD_CUSTOM_BEGIN = 0x0B
CMD_SLEEP = 0x0C
CMD_RESPONSE = 0x0D
CMD_STATUS = 0x0E
CMD_RESET_KEYS = 0x0F
CMD_FN_SWITCH = 0x10
CMD_FRAME_BASE = 0xF0   # 0xF0..0xF5: live (non-persistent) LED frame
CMD_CUSTOM_BASE = 0xF6  # 0xF6..0xFB: custom-mode per-key colours (persistent)

LED_SLOTS = 6 * CHUNK // 3  # 108 RGB triplets


class DeviceError(RuntimeError):
    pass


@dataclass
class HidInterface:
    path: str
    product_id: int
    interface: str
    is_control: bool
    bus: int = 0x03

    @property
    def connection(self) -> str:
        if self.bus == 0x05:
            return "Bluetooth"
        return PRODUCTS.get(self.product_id, f"PID {self.product_id:04x}")


def _is_control_descriptor(desc: bytes) -> bool:
    # Usage Page (Vendor 0xFF02) followed by Usage (0x02) -- the collection
    # DeviceDriver.exe selects in sub_43fd60.
    return bytes([0x06, 0x02, 0xFF, 0x09, 0x02]) in desc


def find_interfaces() -> list[HidInterface]:
    found = []
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(os.path.join(node, "device/uevent")).read()
            hid_id = next(l for l in uevent.splitlines() if l.startswith("HID_ID="))
            bus, vid, pid = (int(x, 16) for x in hid_id.split("=")[1].split(":"))
            desc = open(os.path.join(node, "device/report_descriptor"), "rb").read()
            # Known USB ids, or any other link (e.g. Bluetooth) from the same
            # vendor that exposes the config collection.
            if vid != VENDOR_ID or (pid not in PRODUCTS and not _is_control_descriptor(desc)):
                continue
            iface = os.path.basename(os.path.realpath(os.path.join(node, "device/..")))
        except (OSError, StopIteration, ValueError):
            continue
        found.append(HidInterface("/dev/" + os.path.basename(node), pid, iface,
                                  _is_control_descriptor(desc), bus))
    return found


def find_control_interface() -> HidInterface:
    controls = [i for i in find_interfaces() if i.is_control]
    if not controls:
        raise DeviceError("no AK820 Max Plus control interface found "
                          f"(looked for {VENDOR_ID:04x}:a036 / {VENDOR_ID:04x}:8fff)")
    # Prefer the wired connection if both the cable and the dongle are present.
    controls.sort(key=lambda i: i.product_id != 0xA036)
    return controls[0]


def encode_delay(release: bool, delay_ms: int) -> int:
    """Macro event timing byte, mirroring sub_4232d0.

    bit7 = release, bits6..5 = time base, bits4..0 = count.
    """
    d = min(max(delay_ms, 0), 31000)
    hi = lo = 0
    if d <= 10:
        count = 1
    elif d <= 310:
        count = d // 10
    elif d <= 1550:
        count, lo = d // 50, 1
    elif d <= 3100:
        count, lo = d // 100, 1  # vendor driver uses the same base as /50 here
    else:
        count, hi, lo = d // 1000, 1, 1
    return (release << 7) | (hi << 6) | (lo << 5) | (count & 0x1F)


@dataclass
class Status:
    battery: int | None
    power: int  # keys.POWER_STATES

    @property
    def power_name(self) -> str:
        return keys.POWER_STATES.get(self.power, f"unknown ({self.power})")

    @property
    def online(self) -> bool:
        return self.power != 0

    @property
    def on_charger(self) -> bool:
        return self.power in (1, 3)


SIMULATED_STATUS = (MAGIC + bytes([CMD_STATUS, 87, 2])).ljust(REPORT_LEN, b"\x00")


class Keyboard:
    def __init__(self, path: str | None = None, dry_run: bool = False, log=None):
        self.dry_run = dry_run
        self.log = log
        self.fd = None
        self.path = path
        if dry_run:
            self.path = path or "(dry-run)"
            return
        if self.path is None:
            self.path = find_control_interface().path
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise DeviceError(f"permission denied on {self.path}; install the udev rule "
                              "(see README) or run with sudo") from e

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- transport ---------------------------------------------------------

    def _drain(self):
        while self.fd is not None and select.select([self.fd], [], [], 0)[0]:
            try:
                os.read(self.fd, REPORT_LEN)
            except BlockingIOError:
                break

    def _write(self, report: bytes):
        assert len(report) == REPORT_LEN
        if self.log:
            self.log(report)
        if self.dry_run:
            return
        os.write(self.fd, b"\x00" + report)

    def _read(self, timeout: float) -> bytes | None:
        if self.dry_run:
            return SIMULATED_STATUS
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        return os.read(self.fd, REPORT_LEN)

    def send(self, cmd: int, args: bytes = b"", reply: bool = False,
             timeout: float = 0.5) -> bytes | None:
        report = (MAGIC + bytes([cmd]) + args).ljust(REPORT_LEN, b"\x00")
        self._drain()
        self._write(report)
        if not reply:
            return None
        time.sleep(0.1)
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            resp = self._read(left)
            if resp is None:
                break
            if resp[:4] == MAGIC and resp[4] == cmd:
                return resp
        return None

    def _send_chunks(self, base_cmd: int, data: bytes, count: int, gap: float):
        data = data.ljust(count * CHUNK, b"\x00")
        for i in range(count):
            self.send(base_cmd + i, data[i * CHUNK:(i + 1) * CHUNK])
            time.sleep(gap)

    # -- commands ----------------------------------------------------------

    def status(self) -> Status | None:
        resp = self.send(CMD_STATUS, reply=True)
        if resp is None:
            return None
        battery = resp[5] if resp[5] <= 100 else None
        return Status(battery=battery, power=resp[6])

    def set_light(self, mode: int, brightness: int = keys.DEFAULT_BRIGHTNESS,
                  speed: int = keys.DEFAULT_SPEED, direction: int = 0,
                  color: int = keys.RAINBOW):
        for name, v in (("brightness", brightness), ("speed", speed)):
            if not 1 <= v <= keys.MAX_LEVEL:
                raise ValueError(f"{name} must be 1..{keys.MAX_LEVEL}")
        if direction not in (0, 1):
            raise ValueError("direction must be 0 (left to right) or 1 (right to left)")
        if not 0 <= color < len(keys.PALETTE):
            raise ValueError(f"colour index must be 0..{len(keys.PALETTE) - 1}")
        self.send(CMD_LIGHT, bytes([mode - 1, brightness - 1, speed - 1, direction, color]))
        time.sleep(0.01)

    @staticmethod
    def _led_buffer(colors: dict[int, tuple[int, int, int]]) -> bytes:
        buf = bytearray(LED_SLOTS * 3)
        for led, (r, g, b) in colors.items():
            if 0 <= led < LED_SLOTS:
                buf[led * 3:led * 3 + 3] = bytes((r, g, b))
        return bytes(buf)

    def set_custom_colors(self, colors: dict[int, tuple[int, int, int]],
                          brightness: int = keys.DEFAULT_BRIGHTNESS):
        """Switch to custom mode and store per-LED colours (sub_411130/sub_429ed0).

        07 17 .. -> 0B -> F6..FB is the sequence confirmed on hardware.
        """
        self.set_light(keys.CUSTOM_MODE, brightness)
        self.send(CMD_CUSTOM_BEGIN)
        time.sleep(0.01)
        self._send_chunks(CMD_CUSTOM_BASE, self._led_buffer(colors), 6, 0.003)

    def lights_off(self):
        """No off command exists; an all-black custom map does the job."""
        self.set_custom_colors({}, brightness=1)

    def enter_live_mode(self, mode: int = keys.MUSIC_MODE):
        """Select a host-driven mode (22 music / 23 screen) and open the frame stream.

        Frames are not stored.  When they stop, the keyboard goes back to its
        stored effect on its own (hardware-verified at 20 fps).
        """
        self.set_light(mode, 5, 3)
        self.send(CMD_STREAM_BEGIN)  # the vendor app waits for a reply that never comes
        time.sleep(0.05)

    def send_frame(self, colors: dict[int, tuple[int, int, int]]):
        """One live LED frame (sub_427980).  Call enter_live_mode() first."""
        buf = self._led_buffer(colors)
        for i in range(6):
            self._write((MAGIC + bytes([CMD_FRAME_BASE + i]) +
                         buf[i * CHUNK:(i + 1) * CHUNK]).ljust(REPORT_LEN, b"\x00"))

    def set_sleep(self, option: int):
        """1 = 5 min, 2 = 15 min, 3 = 30 min, 4 = never."""
        self.send(CMD_SLEEP, bytes([option]))

    def set_response(self, gear: int):
        """Key response time gear 1..3 (1 = fastest)."""
        self.send(CMD_RESPONSE, bytes([gear]))

    def set_fn_switch(self, fn_mode: bool):
        self.send(CMD_FN_SWITCH, bytes([1 if fn_mode else 0]))

    def remap(self, layer: int, src: int, dst: int):
        """layer 0 = base, 1 = Fn.  dst = HID usage or media code (0 = disabled?)."""
        self.send(CMD_REMAP, bytes([layer + 1, src, dst]))
        time.sleep(0.2)

    def set_macro(self, layer: int, src: int, events: list[tuple[int, bool, int]],
                  repeat: int = 1):
        """events: (hid code, release?, delay ms).  sub_4106b0 / sub_410c10."""
        if len(events) > 60:
            raise ValueError("at most 60 macro events")
        body = bytearray([layer + 1, src, repeat & 0xFF, len(events)])
        for code, release, delay in events:
            body += bytes([code, encode_delay(release, delay)])
        self._send_chunks(CMD_KEY_CHUNK0, bytes(body), 3, 0.02)
        time.sleep(0.15)

    def reset_keys(self):
        self.send(CMD_RESET_KEYS)
        time.sleep(0.1)

    def factory_reset(self):
        self.send(CMD_FACTORY_RESET)
        time.sleep(0.1)

    def raw(self, data: bytes, reply: bool = False) -> bytes | None:
        return self.send(data[0], data[1:], reply=reply)
