"""Approximate on-screen previews of the firmware's built-in effects.

These only imitate what the keyboard draws; they are never sent to it.
The effect formulas are adapted from prasoondev/ajazz-linux (preview.py),
MIT License, Copyright (c) 2026 prasoon.
"""

from __future__ import annotations

import colorsys
import math

from . import keys

RGB = tuple[int, int, int]

_ROW = {led: row for _, _, led, row, _ in keys.PHYSICAL_KEYS}
_CX = {led: x + w / 2 for led, (x, y, w, h) in keys.KEY_RECTS.items()}
_CY = {led: y + h / 2 for led, (x, y, w, h) in keys.KEY_RECTS.items()}
_X0, _X1 = min(_CX.values()), max(_CX.values())
_Y0, _Y1 = min(_CY.values()), max(_CY.values())
# led -> (u, v, row) with u: 0 left .. 1 right, v: 0 top .. 1 bottom
POS = {led: ((_CX[led] - _X0) / (_X1 - _X0), (_CY[led] - _Y0) / (_Y1 - _Y0), _ROW[led])
       for led in keys.KEY_RECTS}


def _rand(n: int, salt: int = 0) -> float:
    h = (n * 2654435761 + salt * 40503) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return (h & 0xFFFF) / 0xFFFF


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def brightness_scale(level: int) -> float:
    return 0.18 + 0.82 * (level - 1) / 4


def frame(mode: int, brightness: int, speed: int, direction: int, color: int, t: float,
          custom: dict[int, RGB] | None = None) -> dict[int, RGB]:
    """Colours for every LED at time t (seconds)."""
    if mode == keys.CUSTOM_MODE:
        b = brightness_scale(brightness)
        return {led: tuple(int(c * b) for c in rgb) for led, rgb in (custom or {}).items()}
    if mode not in keys.LIGHT_MODES or mode in (keys.MUSIC_MODE, keys.SCREEN_MODE):
        return {}
    attr = keys.LIGHT_MODES[mode][1]
    sp = 0.25 + 0.3 * (speed - 1) if attr & keys.ATTR_SPEED else 0.5
    fixed = None
    if attr & keys.ATTR_COLOR and color != keys.RAINBOW:
        fixed = tuple(c / 255 for c in keys.PALETTE[color][1])
    left = bool(attr & keys.ATTR_DIRECTION) and direction == 1
    bscale = brightness_scale(brightness) if attr & keys.ATTR_BRIGHTNESS else 1.0
    out = {}
    for led, (u, v, row) in POS.items():
        uu = 1 - u if left else u
        hue, k = None, 1.0
        if mode == 1:
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (uu * 1.6 - t * sp))) ** 2
            hue = u * 0.8 + t * 0.05
        elif mode == 2:
            k = max(0.0, math.sin(2 * math.pi * (t * sp * 0.6 + _rand(led)))) ** 10
            hue = _rand(led, 1)
        elif mode == 3:
            vv = 1 - v if left else v
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (vv * 1.4 - t * sp))) ** 2
            hue = v * 0.8 + t * 0.05
        elif mode == 4:
            d = abs(u - 0.5) * 2
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (d * 1.5 - t * sp))) ** 2
            hue = d * 0.7 + t * 0.05
        elif mode == 5:
            hue = t * sp * 0.15
        elif mode == 6:
            a = math.atan2((v - 0.5) * 0.4, u - 0.5) / (2 * math.pi)
            hue = a + math.hypot(u - 0.5, v - 0.5) - t * sp * 0.25
            k = 0.6 + 0.4 * math.sin(2 * math.pi * (a * 3 + t * sp * 0.5))
        elif mode == 7:
            hue = u * 0.85
        elif mode == 8:
            k = 0.5 - 0.5 * math.cos(2 * math.pi * t * sp * 0.4)
            hue = t * 0.03
        elif mode == 9:
            p = (t * sp * 0.5) % 1.0
            k = max(_clamp(1 - abs(uu - p) * 7), _clamp(1 - abs(v - p) * 5))
            hue = p + u * 0.3
        elif mode == 11:
            k = (0.5 - 0.5 * math.cos(2 * math.pi * (t * sp * 0.4 + _rand(led)))) ** 2
            hue = _rand(led, 2)
        elif mode == 12:
            hue = uu * 0.7 + v * 0.3 - t * sp * 0.25
            if fixed:
                k = 0.5 + 0.5 * math.sin(2 * math.pi * (uu + v * 0.5 - t * sp * 0.5))
        elif mode == 15:
            ph = 0.5 + 0.5 * math.sin(2 * math.pi * t * sp * 0.4)
            k = ph if row < 3 else 1 - ph
            hue = 0.0 if row < 3 else 0.6
        elif mode == 16:
            col = round(u * 15)
            pos = (t * sp * 0.6 + _rand(col, 3)) % 1.4 - 0.2
            k = _clamp(1 - (pos - v) * 3) * _clamp(1 + (pos - v) * 12) if v <= pos + 0.1 else 0
            hue = _rand(col, 4)
        elif mode == 17:
            a = math.atan2((v - 0.5) * 0.4, u - 0.5)
            k = (0.5 + 0.5 * math.cos(4 * a - t * sp * 3)) ** 3
            hue = a / (2 * math.pi) + t * 0.05
        elif mode == 18:
            y = 0.5 + 0.4 * math.sin(2 * math.pi * (uu - t * sp * 0.4))
            k = _clamp(1 - abs(v - y) * 4)
            hue = uu
        elif mode == 19:
            p = (t * sp * 0.45) % 1.2 - 0.1
            k = _clamp(1 - abs(uu - p) * 6)
            hue = p
        rgb = fixed if fixed is not None else colorsys.hsv_to_rgb(
            (hue if hue is not None else u) % 1.0, 1.0, 1.0)
        f = _clamp(k) * bscale
        out[led] = (int(rgb[0] * 255 * f), int(rgb[1] * 255 * f), int(rgb[2] * 255 * f))
    return out
