import pytest

from ak820 import keys
from ak820.cli import parse_macro_events
from ak820.protocol import MAGIC, Keyboard, encode_delay


def capture():
    sent = []
    return Keyboard(dry_run=True, log=sent.append), sent


@pytest.mark.parametrize("release,ms,expected", [
    (False, 5, 0x01),      # <= 10 ms clamps to count 1
    (False, 20, 0x02),     # 10 ms base
    (True, 310, 0x9F),     # release bit + 31 x 10 ms
    (False, 500, 0x2A),    # 50 ms base
    (False, 2000, 0x34),   # vendor quirk: /100 but same base bits as /50
    (True, 5000, 0xE5),    # 1000 ms base
])
def test_encode_delay(release, ms, expected):
    assert encode_delay(release, ms) == expected


def test_light_packet():
    kb, sent = capture()
    kb.set_light(7, brightness=5, speed=3, direction=0, color=2)
    assert sent == [(MAGIC + bytes([0x07, 6, 4, 2, 0, 2])).ljust(64, b"\0")]


def test_light_rejects_bad_level():
    kb, _ = capture()
    with pytest.raises(ValueError):
        kb.set_light(1, brightness=0)


def test_custom_colors_sequence():
    kb, sent = capture()
    esc = keys.LED_BY_CODE[keys.key_code("esc")]
    kb.set_custom_colors({esc: (255, 0, 0)})
    cmds = [p[4] for p in sent]
    assert cmds == [0x07, 0x0B, 0x09, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB]
    assert sent[0][5] == keys.CUSTOM_MODE - 1
    first_chunk = sent[3][5:5 + 54]
    assert first_chunk[esc * 3:esc * 3 + 3] == b"\xff\x00\x00"


def test_remap_packet():
    kb, sent = capture()
    kb.remap(1, keys.key_code("f1"), keys.target_code("playpause"))
    assert sent[0][:8] == MAGIC + bytes([0x04, 0x02, 0x3A, 0xEE])


def test_macro_chunks():
    kb, sent = capture()
    events = parse_macro_events(["+lctrl", "c", "-lctrl@500"], 10)
    kb.set_macro(0, keys.key_code("f12"), events, repeat=2)
    assert [p[4] for p in sent] == [0x00, 0x01, 0x02]
    assert sent[0][5:9] == bytes([0x01, 0x45, 0x02, 4])
    assert sent[0][9:17] == bytes([0xE0, 0x01, 0x06, 0x01, 0x06, 0x81, 0xE0, 0xAA])


def test_key_lookup():
    assert keys.key_code("Esc") == 0x29
    assert keys.key_code("0x2c") == 0x2C
    assert keys.key_code("fn") == keys.FN_CODE
    assert keys.target_code("volup") == 0xEA
    with pytest.raises(KeyError):
        keys.key_code("nope")


def test_every_physical_key_has_unique_led():
    leds = [led for _, _, led, _, _ in keys.PHYSICAL_KEYS]
    assert len(leds) == len(set(leds)) == 82
    assert max(leds) < 108
