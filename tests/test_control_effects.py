import pytest

from openajazz import control, effects, keys, state
from openajazz.protocol import Keyboard


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


def _lit(frame, threshold=40):
    return {led for led, rgb in frame.items() if max(rgb) > threshold}


ROW_OF = {led: row for _, _, led, row, _ in keys.PHYSICAL_KEYS}
K = keys.LED_BY_CODE[keys.key_code("k")]


def test_ejection_only_moves_the_pressed_row():
    # long after the auto presses start, use a real press and look just after it
    frame = effects.frame(4, 5, 3, 0, keys.RAINBOW, t=0.25, presses=[(K, 0.0)])
    rows = {ROW_OF[led] for led in _lit(frame)}
    assert ROW_OF[K] in rows
    assert K not in _lit(frame)            # the wave has left the key itself
    lit_k_row = {led for led in _lit(frame) if ROW_OF[led] == ROW_OF[K]}
    us = [effects.POS[led][0] for led in lit_k_row]
    k_u = effects.POS[K][0]
    assert min(us) < k_u < max(us)         # it travels both ways


def test_jiangshan_moves_the_whole_column():
    frame = effects.frame(12, 5, 3, 0, keys.RAINBOW, t=0.25, presses=[(K, 0.0)])
    assert len({ROW_OF[led] for led in _lit(frame)}) == 6


def test_top_and_bottom_chunks_move_opposite_ways():
    def centre(frame, rows):
        lit = [effects.POS[l][0] for l in _lit(frame) if ROW_OF[l] in rows]
        return sum(lit) / len(lit)
    a = effects.frame(15, 5, 3, 0, keys.RAINBOW, t=1.5)
    b = effects.frame(15, 5, 3, 0, keys.RAINBOW, t=1.8)
    assert centre(b, {0, 1, 2}) > centre(a, {0, 1, 2})
    assert centre(b, {3, 4, 5}) < centre(a, {3, 4, 5})


def test_galloping_lights_one_row_at_a_time():
    for t in (0.4, 1.1, 2.3, 3.7):
        frame = effects.frame(19, 5, 3, 0, keys.RAINBOW, t=t)
        assert len({ROW_OF[led] for led in _lit(frame)}) <= 1


def test_kaleidoscope_rings_move_outward():
    centre = min(effects.POS, key=lambda l: abs(effects.POS[l][0] - 0.5) + abs(effects.POS[l][1] - 0.5))
    def ring_phase(t):
        return effects.frame(6, 5, 3, 0, keys.RAINBOW, t=t)[centre]
    # brightness at the centre oscillates: the pattern isn't static
    assert ring_phase(0.0) != ring_phase(0.3)


def test_cross_waves_come_from_both_edges():
    frame = effects.frame(9, 5, 3, 0, keys.RAINBOW, t=0.65)  # waves just entered
    us = [effects.POS[l][0] for l in _lit(frame)]
    assert min(us) < 0.15 and max(us) > 0.85
