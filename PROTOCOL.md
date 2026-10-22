# AJAZZ AK820 Max Plus HID protocol

Recovered from the vendor package
`AJAZZ_AK820_MAX_PLUS_Tripe_Mode_RGB_Keyboard_Drive_XY_version__V1.0.4.6.rar`
(Inno Setup 6.3 installer → `DeviceDriver.exe`, sha256 `ec1ce433…617f`, x86).
Addresses below are virtual addresses in `DeviceDriver.exe` unless noted.

Legend: **observed** = read directly from code/data; **inferred** = reasoned
from context; **verified** = confirmed on a real keyboard (hardware test log in
[prasoondev/ajazz-linux](https://github.com/prasoondev/ajazz-linux/blob/main/docs/REPORT.md)).

## Transport

| | |
|---|---|
| VID:PID | `1a2c:a036` wired, `1a2c:8fff` 2.4G dongle (`config.xml`) |
| Interface | HID collection with usage page `0xFF02`, usage `0x02` (`sub_43fd60`). Dongle: USB interface 0. |
| Report | 64-byte output report, report ID 0, written with `WriteFile` (`sub_441250`). On Linux: `write(fd, 00 + 64 bytes)`. |
| Header | `AA 55 CC 33 <cmd> <args…>`, zero padded |
| Reply | Same header and `cmd` echoed (`sub_428790` checks `AA 55 CC 33`). The sender sleeps 100 ms, then reads with a 500 ms timeout (`sub_43f900` with wait=1). |

The `HidD_SetFeature` path (`sub_43f6c0`, packets starting `07 xx`) and the
`BB AA 99 88` packets are for other `device_type` families; this keyboard is
`device_type="301"`, which uses the output-report path (status polling is
gated on 300 ≤ type < 400 in `sub_428790`; reset dispatches on type > 200 in `sub_428700`).

## Commands

| cmd | args (byte 5…) | meaning | evidence |
|---|---|---|---|
| `00`–`02` | 54-byte chunks of a 162-byte key block (see Macro) | macro / shortcut on a key | `sub_4106b0` (observed) |
| `04` | `layer+1, src_key, value` | single-code key assignment | `sub_410590` (observed) |
| `07` | `mode-1, brightness-1, speed-1, direction, colorindex` | lighting effect | `sub_411130`, columns from `sub_4067c0` (**verified**, all 16 effects) |
| `08` | – | restore factory settings | `sub_411270`, then UI refresh (observed) |
| `09` | – | begin live LED stream; the vendor app waits for a reply that never comes | `sub_427980`, `sub_429ed0` (**verified**) |
| `0A` | – | unknown; sent from a UI message handler (`sub_421e30`) | unknown |
| `0B` | – | sent before custom-mode colours when mode = 24 | `sub_411130` (**verified**) |
| `0C` | `1..4` = 5 / 15 / 30 min / never | sleep timer (`sleeptime`) | `sub_411d10` sends `MComboBox::GetCurData()`; items added with `AddItem(text, data=1..4, …)` at `0x42e7e6` (observed) |
| `0D` | `1..3` | key response gear (`key_responsetime`) | `sub_411e50`, items at `0x42ed78` (observed) |
| `0E` | – (waits for reply) | status query, see below | `sub_428790`, `sub_410090`, probe in `sub_43fd60` (**verified**) |
| `0F` | – | reset key assignments, sent before re-uploading all keys | `sub_4101a0`, `sub_410140` (observed; meaning inferred) |
| `10` | `0` normal / `1` Fn | Fn switch (`fn_switch`) | `sub_418c70`, `sub_418d40` (observed; no visible effect in hardware tests) |
| `F0`–`F5` | 54 bytes each | live LED frame, 108 × RGB, not stored | `sub_427980` (**verified** at 20 fps after `07 15 …`, `09`; reverts to the stored effect when frames stop) |
| `F6`–`FB` | 54 bytes each | custom-mode per-key colours, 108 × RGB | `sub_429ed0` (**verified**, LED map correct) |

### Status reply (`0E`)

`resp[5]` = battery percent (only used if ≤ 100). `resp[6]` = power state:
`0` = no data (nothing behind the dongle), `1` = charging, `2` = on battery,
`3` = fully charged (**verified**: `64 03` on the cable, `61 01` charging over
2.4G). The vendor app polls this every 5 s (`0x1388` ms).

### Lighting

Fields come from `t_light_data`: `mode, brightness, speed, direction, colorful,
colorindex` (`sub_4067c0`). `colorful` is **not** sent. Brightness and speed
range 1–5 in the UI and are sent minus 1. Mode numbers and the meaning of the
attribute bits come from `layouts/kb-k600t.xml`: 1–19 effects, 22/23 music or
screen rhythm (host-driven via `F0`–`F5`), 24 custom per-key (`mode-1 = 0x17`).
Colour index (vendor buttons `0x58`–`0x5F`, **verified**): 0 red, 1 green,
2 blue, 3 yellow, 4 magenta, 5 cyan, 6 white, 7 rainbow. Direction (**verified**):
0 = left to right, 1 = right to left.

There is no "off" command; an all-black custom map does the job.

### Per-key colours

The buffer is indexed by LED index (`key_index` in the layout XML, through a
keycode→index map at `this+0x64c`). Each slot is 3 bytes, copied from the low 3
bytes of a `COLORREF` (R, G, B). Custom mode sequence (`sub_411130`):
`07 17 …` → `0B` → (10 ms) → `F6`…`FB` with 3 ms gaps (**verified**; the
vendor's optional `09` in between isn't needed).

Live frames (music/screen modes, painting preview): `07 15 …` (mode 22) →
`09` → `F0`…`F5` per frame.

### Key assignment (`04`)

`layer` is 0 base / 1 Fn. `src_key` is the physical key's HID usage (`code` in
the layout XML; Fn = `0xAF`). `value` is `macro_value`: a HID usage for
keyboard keys, or a media code `0xE8`–`0xF9` (from the `XYUI.dll`
`KeyFuncControl::InitItemInfo` item data). The record is only sent when
`macro_type ∉ {0, 3, 7}`. With value ≤ 0, byte 7 stays 0, which probably
disables the key (unverified).

### Macro (`00`–`02`)

162-byte block, split into three 54-byte packets with 20 ms gaps:

```
[0] layer+1   [1] src_key   [2] repeat (play_times, or 1 for shortcuts)
[3] n_events  [4..] n × (hid_usage, timing)
```

Timing byte (`sub_4232d0`): bit 7 = release, bits 6–5 = time base, bits 4–0 =
count. ≤10 ms → `count 1`; ≤310 → ms/10, base 00; ≤1550 → ms/50, base 01;
≤3100 → ms/100, base 01 (same base as /50; this looks like a vendor bug);
≤31000 → ms/1000, base 11. Recorded Windows VK codes are converted to HID usages
by `sub_441850`. Only key down/up records (types 2/3) are encoded. Mouse
events are dropped.

### Restoring one key

The vendor app never sends a "default" target for a single key. It sends `0F`
and then re-uploads every remaining remap and macro (`sub_4101a0`). openajazz
does the same, so restoring a key doesn't depend on guessing what target `0`
means.

### Bluetooth

`config.xml` only defines USB (mode 0) and 2.4G (mode 2); the vendor app has no
Bluetooth mode, no pairing commands and no way to list paired hosts. Settings
can only be changed over the cable or the dongle.

## Not covered

Firmware update (separate `700N(0X3B4F)…exe` updater), music/screen-rhythm
analysis (host side), command `0A`, mouse-button assignments.
