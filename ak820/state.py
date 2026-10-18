"""Local copy of what we last sent to the keyboard.

The firmware has no read-back command that we know of, so the TUI keeps its
own record in $XDG_CONFIG_HOME/ak820ctl to start where you left off.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import keys

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ak820ctl"
STATE_FILE = CONFIG_DIR / "state.json"
PRESET_DIR = CONFIG_DIR / "presets"

Colors = dict[int, tuple[int, int, int]]


def default_state() -> dict:
    return {
        "light": {"mode": 7, "brightness": keys.DEFAULT_BRIGHTNESS,
                  "speed": keys.DEFAULT_SPEED, "direction": 0, "color": 0},
        "colors": {},
        "remaps": {},   # "layer:src" -> dst
        "macros": {},   # "layer:src" -> {"events": str, "repeat": int}
        "settings": {"sleep": 1, "response": 1, "fn": False},
    }


def load() -> dict:
    data = default_state()
    try:
        saved = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return data
    for section, value in saved.items():
        if isinstance(data.get(section), dict) and isinstance(value, dict):
            data[section].update(value)
    return data


def save(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(STATE_FILE)


def colors_from_json(raw: dict) -> Colors:
    return {int(led): tuple(rgb) for led, rgb in raw.items()}


def colors_to_json(colors: Colors) -> dict:
    return {str(led): list(rgb) for led, rgb in colors.items()}


def _preset_path(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("preset name is empty")
    return PRESET_DIR / f"{slug}.json"


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def save_preset(name: str, colors: Colors) -> str:
    path = _preset_path(name)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(colors_to_json(colors), indent=2))
    return path.stem


def load_preset(name: str) -> Colors:
    return colors_from_json(json.loads(_preset_path(name).read_text()))
