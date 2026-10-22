import math
import struct

import pytest

np = pytest.importorskip("numpy")

from openajazz import keys  # noqa: E402
from openajazz.music import BANDS, FFT_SIZE, RATE, Analyzer, Renderer  # noqa: E402


def tone(freq: float, amplitude: float = 0.8) -> bytes:
    samples = [int(32767 * amplitude * math.sin(2 * math.pi * freq * i / RATE))
               for i in range(FFT_SIZE)]
    return struct.pack(f"<{FFT_SIZE}h", *samples)


def test_bass_tone_lights_low_bands():
    an = Analyzer()
    for _ in range(5):
        an.update(tone(60))
    assert an.levels[:3].max() > 0.8
    assert an.levels[-4:].max() < an.levels[:3].max()
    assert an.bass > 0.5


def test_silence_is_dark():
    an = Analyzer()
    an.update(bytes(FFT_SIZE * 2))
    assert an.levels.max() == 0


@pytest.mark.parametrize("style", ["spectrum", "pulse", "wave"])
def test_renderer_covers_every_key(style):
    frame = Renderer(style).frame(np.linspace(0, 1, BANDS), 0.7)
    assert set(frame) == set(keys.KEY_RECTS)


def test_renderer_single_colour():
    frame = Renderer("pulse", color=(255, 0, 0)).frame(np.ones(BANDS), 1.0)
    assert all(g == 0 and b == 0 for _, g, b in frame.values())
