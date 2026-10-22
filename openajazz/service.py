"""Running music sync without a terminal: a detached process, or a systemd user
service that starts it at login."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "openajazz"
PID_FILE = STATE_DIR / "music.pid"
LOG_FILE = STATE_DIR / "music.log"
UNIT_NAME = "openajazz-music.service"
UNIT_PATH = (Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
             / "systemd" / "user" / UNIT_NAME)


def executable() -> list[str]:
    """How to start openajazz again from a detached process or a service."""
    if os.environ.get("APPIMAGE"):  # running from the AppImage
        return [os.environ["APPIMAGE"]]
    found = shutil.which("openajazz")
    if found:
        return [os.path.realpath(found)]
    return [sys.executable, "-m", "openajazz"]


def music_argv(style: str, color: str | None, sensitivity: float, fps: int,
               device: str | None, dry_run: bool = False) -> list[str]:
    argv = executable() + (["--device", device] if device else []) + (["-n"] if dry_run else []) + [
        "music", "--quiet", "--style", style, "--sensitivity", str(sensitivity), "--fps", str(fps)]
    if color:
        argv += ["--color", color]
    return argv


# -- detached process --------------------------------------------------------

def _alive(pid: int) -> bool:
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    return b"music" in cmdline


def running_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    if _alive(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)
    return None


def start_background(argv: list[str]) -> int:
    """Start music sync detached from the terminal; raises if it dies right away."""
    if running_pid():
        raise RuntimeError("music sync is already running (openajazz music --stop)")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w") as log:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
    PID_FILE.write_text(str(proc.pid))
    time.sleep(1.5)  # catch the obvious failures: no numpy, no audio, no keyboard
    if proc.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        tail = LOG_FILE.read_text().strip().splitlines()[-3:]
        raise RuntimeError("music sync stopped right away: " + (" / ".join(tail) or "no output"))
    return proc.pid


def stop_background(timeout: float = 4.0) -> bool:
    """Stop a detached run (it restores the lighting itself).  True if one was running."""
    pid = running_pid()
    if not pid:
        return False
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _alive(pid):
        os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    return True


# -- systemd user service ----------------------------------------------------

def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    if not shutil.which("systemctl"):
        raise RuntimeError("autostart needs systemd (systemctl not found)")
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True,
                          check=check)


def unit_text(argv: list[str]) -> str:
    exec_start = " ".join(f'"{a}"' if " " in a else a for a in argv)
    return f"""[Unit]
Description=openajazz music sync (AJAZZ keyboard)
After=graphical-session.target pipewire-pulse.service
PartOf=graphical-session.target

[Service]
ExecStart={exec_start}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target
"""


def enable_autostart(argv: list[str]):
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(unit_text(argv))
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", UNIT_NAME)


def disable_autostart() -> bool:
    if not UNIT_PATH.exists():
        return False
    _systemctl("disable", "--now", UNIT_NAME, check=False)
    UNIT_PATH.unlink()
    _systemctl("daemon-reload", check=False)
    return True


def autostart_status() -> str:
    if not UNIT_PATH.exists():
        return "off"
    state = _systemctl("is-active", UNIT_NAME, check=False).stdout.strip() or "unknown"
    return f"on ({state})"
