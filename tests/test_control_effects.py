import pytest

from ak820 import control, effects, keys, state
from ak820.protocol import Keyboard


def session():
    sent = []
    return Keyboard(dry_run=True, log=sent.append), state.default_state(), sent


def test_lights_off_then_on_restores_effect():
    kb, st, sent = session()
    light = {"mode": 8, "brightness": 3, "speed": 2, "direction": 0, "color": 5}
    control.apply_light(kb, st, light)
    control.lights_off(kb, st)
    assert st["lights_off"] is True
    sent.clear()
    control.lights_on(kb, st)
    assert sent[0][4:10] == bytes([0x07, 7, 2, 1, 0, 5])
    assert st["lights_off"] is False


def test_lights_on_restores_custom_colors():
    kb, st, sent = session()
    control.upload_custom(kb, st, {15: (9, 8, 7)}, 4)
    control.lights_off(kb, st)
    sent.clear()
    control.lights_on(kb, st)
    assert [p[4] for p in sent][:2] == [0x07, 0x0B]
    assert sent[2][5 + 45:5 + 48] == bytes([9, 8, 7])


def test_toggle():
    kb, st, _ = session()
    assert control.toggle_lights(kb, st) is False
    assert control.toggle_lights(kb, st) is True


def test_restore_key_replays_the_rest():
    kb, st, sent = session()
    control.remap(kb, st, 0, 0x39, 0x29)
    control.remap(kb, st, 1, 0x3A, 0xEE)
    control.set_macro(kb, st, 0, 0x45, "+lctrl c -lctrl")
    sent.clear()
    control.restore_key(kb, st, 0, 0x39)
    cmds = [p[4] for p in sent]
    assert cmds[0] == 0x0F                      # reset first
    assert 0x04 in cmds and cmds.count(0x04) == 1  # only the Fn remap is re-sent
    assert cmds[-3:] == [0x00, 0x01, 0x02]      # then the macro
    assert "0:57" not in st["remaps"]


def test_settings_and_factory_reset():
    kb, st, sent = session()
    control.apply_settings(kb, st, 3, 2, True)
    assert [p[4:6] for p in sent] == [bytes([0x0C, 3]), bytes([0x0D, 2]), bytes([0x10, 1])]
    control.factory_reset(kb, st)
    assert st == state.default_state()


@pytest.mark.parametrize("mode", [m for m in keys.LIGHT_MODES if m not in (22, 23, 24)])
def test_every_effect_preview_renders(mode):
    frame = effects.frame(mode, 5, 3, 1, keys.RAINBOW, t=1.3)
    assert set(frame) == set(keys.KEY_RECTS)
    assert all(0 <= c <= 255 for rgb in frame.values() for c in rgb)


def test_fixed_colour_preview_uses_palette():
    frame = effects.frame(7, 5, 3, 0, keys.palette_index("red"), t=0)
    assert all(g == 0 and b == 0 for _, g, b in frame.values())
