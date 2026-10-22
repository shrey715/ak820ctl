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


# Effects that react to typing.  Previews feed them simulated key presses
# (plus real clicks in the web app).
REACTIVE = {4, 12}
PRESS_EVERY = 0.9
_LEDS = sorted(POS)


def auto_presses(t: float, keep: int = 3) -> list[tuple[int, float]]:
    """A deterministic stream of fake key presses: (led, time pressed)."""
    slot = int(t // PRESS_EVERY)
    return [(_LEDS[int(_rand(s, 7) * len(_LEDS)) % len(_LEDS)], s * PRESS_EVERY)
            for s in range(max(0, slot - keep + 1), slot + 1)]


def _press_wave(u: float, row: int, t: float, sp: float, presses, same_row: bool):
    """Brightest wave front from recent presses: (intensity, hue)."""
    best, hue = 0.0, 0.0
    for led, pt in presses:
        age = t - pt
        if not 0 <= age < 2.2 or led not in POS:
            continue
        pu, _, prow = POS[led]
        if same_row and prow != row:
            continue
        front = age * (0.35 + 0.25 * sp)
        k = _clamp(1 - abs(abs(u - pu) - front) * 9) * (1 - age / 2.2)
        if k > best:
            best, hue = k, pu + age * 0.15
    return best, hue


def frame(mode: int, brightness: int, speed: int, direction: int, color: int, t: float,
          custom: dict[int, RGB] | None = None,
          presses: list[tuple[int, float]] | None = None) -> dict[int, RGB]:
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
    rev = bool(attr & keys.ATTR_DIRECTION) and direction == 1
    bscale = brightness_scale(brightness) if attr & keys.ATTR_BRIGHTNESS else 1.0
    if mode in REACTIVE:
        presses = list(presses or []) + auto_presses(t)
    out = {}
    for led, (u, v, row) in POS.items():
        uu = 1 - u if rev else u
        hue, k = None, 1.0
        if mode == 1:    # left/right ripples
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (uu * 1.6 - t * sp))) ** 2
            hue = u * 0.8 + t * 0.05
        elif mode == 2:  # starry dots
            k = max(0.0, math.sin(2 * math.pi * (t * sp * 0.6 + _rand(led)))) ** 10
            hue = _rand(led, 1)
        elif mode == 3:  # up/down ripples
            vv = 1 - v if rev else v
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (vv * 1.4 - t * sp))) ** 2
            hue = v * 0.8 + t * 0.05
        elif mode == 4:  # bidirectional ejection: a pressed key fires left+right along its row
            k, hue = _press_wave(u, row, t, sp, presses, same_row=True)
        elif mode == 5:  # spectral cycle
            hue = t * sp * 0.15
        elif mode == 6:  # kaleidoscope: rings from the centre outwards
            r = math.hypot(u - 0.5, (v - 0.5) * 0.42) * 2
            k = (0.5 + 0.5 * math.sin(2 * math.pi * (r * 1.8 + (t if rev else -t) * sp))) ** 2
            hue = r * 0.6 - t * 0.05
        elif mode == 7:  # static
            hue = u * 0.85
        elif mode == 8:  # breathing
            k = 0.5 - 0.5 * math.cos(2 * math.pi * t * sp * 0.4)
            hue = t * 0.03
        elif mode == 9:  # cross operation: waves from both edges pass through each other
            p = (t * sp * 0.45) % 1.4 - 0.2
            kl, kr = _clamp(1 - abs(u - p) * 7), _clamp(1 - abs(u - (1 - p)) * 7)
            k = max(kl, kr)
            hue = (0.0 if kl >= kr else 0.55) + t * 0.03
        elif mode == 11:  # single key breathing
            k = (0.5 - 0.5 * math.cos(2 * math.pi * (t * sp * 0.4 + _rand(led)))) ** 2
            hue = _rand(led, 2)
        elif mode == 12:  # jiangshan: a pressed key sends its whole column sideways
            k, hue = _press_wave(u, row, t, sp, presses, same_row=False)
        elif mode == 15:  # top three rows sweep right, bottom three sweep left
            p = (t * sp * 0.4) % 1.5 - 0.25
            c = p if row < 3 else 1 - p
            k = _clamp(1 - max(0.0, abs(u - c) - 0.12) * 10)
            hue = (0.0 if row < 3 else 0.6) + t * 0.02
        elif mode == 16:  # sideways rain: streaks run along each row
            k = 0.0
            for j in range(2):
                x = (t * sp * 0.55 + _rand(row * 3 + j, 11) * 1.4) % 1.4 - 0.2
                d = (x - uu)
                if d >= -0.03:
                    kk = _clamp(1 - d * 5) * _clamp(1 + d * 30)
                    if kk > k:
                        k, hue = kk, _rand(row * 3 + j, 12)
        elif mode == 17:  # windmill
            a = math.atan2((v - 0.5) * 0.4, u - 0.5)
            k = (0.5 + 0.5 * math.cos(4 * a - t * sp * 3)) ** 3
            hue = a / (2 * math.pi) + t * 0.05
        elif mode == 18:  # sine wave
            y = 0.5 + 0.4 * math.sin(2 * math.pi * (uu - t * sp * 0.4))
            k = _clamp(1 - abs(v - y) * 4)
            hue = uu
        elif mode == 19:  # galloping horse: one row at a time, left to right
            cycle = (t * sp * 0.6) % 6
            cur, prog = int(cycle), (cycle % 1) * 1.25
            k = _clamp(1 - (prog - uu) * 3) if row == cur and uu <= prog else 0.0
            hue = row / 6 + t * 0.02
        rgb = fixed if fixed is not None else colorsys.hsv_to_rgb(
            (hue if hue is not None else u) % 1.0, 1.0, 1.0)
        f = _clamp(k) * bscale
        out[led] = (int(rgb[0] * 255 * f), int(rgb[1] * 255 * f), int(rgb[2] * 255 * f))
    return out
