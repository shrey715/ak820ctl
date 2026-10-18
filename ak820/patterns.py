"""Per-key colour pattern generators, computed on the PC side."""

from __future__ import annotations

import colorsys
import random

from . import keys

RGB = tuple[int, int, int]


def key_width(legend: str) -> int:
    """Width in terminal cells, shared with the TUI keyboard map."""
    return 15 if legend == "Space" else 7 if len(legend) > 3 else 5


def _geometry() -> dict[int, tuple[float, float]]:
    """LED index -> (x, y) of the key centre, both normalised to 0..1."""
    centres, x_by_row = {}, {}
    for _, legend, led, row, col in sorted(keys.PHYSICAL_KEYS, key=lambda k: (k[3], k[4])):
        x = x_by_row.get(row, 0)
        w = key_width(legend)
        centres[led] = (x + w / 2, row)
        x_by_row[row] = x + w + 1
    max_x = max(x_by_row.values())
    max_y = max(r for _, r in centres.values())
    return {led: (x / max_x, y / max_y) for led, (x, y) in centres.items()}


GEOMETRY = _geometry()
WASD = {keys.key_code(k) for k in ("w", "a", "s", "d", "up", "down", "left", "right")}


def _hsv(h: float) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0)
    return round(r * 255), round(g * 255), round(b * 255)


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def generate(name: str, primary: RGB, secondary: RGB) -> dict[int, RGB]:
    out = {}
    for code, _, led, _, _ in keys.PHYSICAL_KEYS:
        x, y = GEOMETRY[led]
        if name == "rainbow-horizontal":
            out[led] = _hsv(x * 0.85)
        elif name == "rainbow-vertical":
            out[led] = _hsv(y * 0.75)
        elif name == "rainbow-diagonal":
            out[led] = _hsv((x + y * 0.5) * 0.6)
        elif name == "gradient-horizontal":
            out[led] = _mix(primary, secondary, x)
        elif name == "gradient-vertical":
            out[led] = _mix(primary, secondary, y)
        elif name == "highlight-gaming":
            out[led] = primary if code in WASD else secondary
        elif name == "random":
            out[led] = _hsv(random.random())
        else:  # solid
            out[led] = primary
    return out


PATTERNS = {
    "solid": "solid fill",
    "rainbow-horizontal": "rainbow, left to right",
    "rainbow-vertical": "rainbow, top to bottom",
    "rainbow-diagonal": "rainbow, diagonal",
    "gradient-horizontal": "gradient brush → second, left to right",
    "gradient-vertical": "gradient brush → second, top to bottom",
    "highlight-gaming": "wasd + arrows in brush, rest in second",
    "random": "random hues",
}
