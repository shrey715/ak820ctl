import pytest

from ak820 import keys, patterns, state


@pytest.mark.parametrize("name", list(patterns.PATTERNS))
def test_patterns_cover_every_key(name):
    colors = patterns.generate(name, (255, 0, 0), (0, 0, 255))
    assert set(colors) == set(keys.LED_BY_CODE.values())
    assert all(len(c) == 3 and all(0 <= v <= 255 for v in c) for c in colors.values())


def test_gradient_endpoints():
    colors = patterns.generate("gradient-horizontal", (255, 0, 0), (0, 0, 255))
    esc = keys.LED_BY_CODE[keys.key_code("esc")]
    right = keys.LED_BY_CODE[keys.key_code("right")]
    assert colors[esc][0] > colors[esc][2]      # left side mostly primary
    assert colors[right][2] > colors[right][0]  # right side mostly secondary


def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    data = state.load()
    data["remaps"]["0:57"] = 0x29
    data["colors"] = state.colors_to_json({15: (1, 2, 3)})
    state.save(data)
    loaded = state.load()
    assert loaded["remaps"] == {"0:57": 0x29}
    assert state.colors_from_json(loaded["colors"]) == {15: (1, 2, 3)}
    assert loaded["settings"] == state.default_state()["settings"]


def test_presets(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "PRESET_DIR", tmp_path)
    slug = state.save_preset("My Cool Theme!", {15: (9, 9, 9)})
    assert slug == "my-cool-theme"
    assert state.list_presets() == ["my-cool-theme"]
    assert state.load_preset("my-cool-theme") == {15: (9, 9, 9)}
    with pytest.raises(ValueError):
        state.save_preset("   ", {})
