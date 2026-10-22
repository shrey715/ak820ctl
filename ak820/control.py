"""High-level operations that keep the local state file in sync.

The CLI and the TUI both go through these, so `ak820ctl lights on` restores
whatever either of them last sent.  Callers decide when to `state.save()`.
"""

from __future__ import annotations

from . import keys, state
from .protocol import Keyboard


def parse_macro_events(tokens: list[str], default_delay: int = 10):
    """'+a' press, '-a' release, 'a' tap; optional '@ms' delay suffix."""
    events = []
    for tok in tokens:
        body, _, delay = tok.partition("@")
        delay = int(delay) if delay else default_delay
        if body[:1] in "+-" and len(body) > 1:
            events.append((keys.key_code(body[1:]), body[0] == "-", delay))
        else:
            code = keys.key_code(body)
            events += [(code, False, default_delay), (code, True, delay)]
    return events


def apply_light(kb: Keyboard, st: dict, light: dict):
    kb.set_light(light["mode"], light["brightness"], light["speed"],
                 light["direction"], light["color"])
    st["light"] = dict(light)
    st["lights_off"] = False


def upload_custom(kb: Keyboard, st: dict, colors: state.Colors, brightness: int | None = None):
    brightness = brightness or st["light"]["brightness"]
    kb.set_custom_colors(colors, brightness)
    st["colors"] = state.colors_to_json(colors)
    st["light"] = {**st["light"], "mode": keys.CUSTOM_MODE, "brightness": brightness}
    st["lights_off"] = False


def lights_off(kb: Keyboard, st: dict):
    kb.lights_off()
    st["lights_off"] = True


def lights_on(kb: Keyboard, st: dict):
    """Re-send whatever lighting was active before `off`."""
    light = st["light"]
    if light["mode"] == keys.CUSTOM_MODE:
        kb.set_custom_colors(state.colors_from_json(st["colors"]), light["brightness"])
    elif light["mode"] in (keys.MUSIC_MODE, keys.SCREEN_MODE):
        kb.set_light(7, light["brightness"], light["speed"], 0, keys.RAINBOW)
    else:
        kb.set_light(light["mode"], light["brightness"], light["speed"],
                     light["direction"], light["color"])
    st["lights_off"] = False


def toggle_lights(kb: Keyboard, st: dict) -> bool:
    """Returns True if the lights are now on."""
    if st.get("lights_off"):
        lights_on(kb, st)
        return True
    lights_off(kb, st)
    return False


def remap(kb: Keyboard, st: dict, layer: int, src: int, dst: int):
    kb.remap(layer, src, dst)
    st["remaps"][f"{layer}:{src}"] = dst
    st["macros"].pop(f"{layer}:{src}", None)


def set_macro(kb: Keyboard, st: dict, layer: int, src: int, raw: str, repeat: int = 1):
    kb.set_macro(layer, src, parse_macro_events(raw.split()), repeat)
    st["macros"][f"{layer}:{src}"] = {"events": raw, "repeat": repeat}
    st["remaps"].pop(f"{layer}:{src}", None)


def replay_keys(kb: Keyboard, st: dict):
    """Reset every key, then re-send the remaps and macros we know about.

    This is what the vendor app does (sub_4101a0), so restoring one key never
    depends on guessing what a 'default' target code looks like.
    """
    kb.reset_keys()
    for key, dst in st["remaps"].items():
        layer, src = map(int, key.split(":"))
        kb.remap(layer, src, dst)
    for key, m in st["macros"].items():
        layer, src = map(int, key.split(":"))
        kb.set_macro(layer, src, parse_macro_events(m["events"].split()), m["repeat"])


def restore_key(kb: Keyboard, st: dict, layer: int, src: int):
    st["remaps"].pop(f"{layer}:{src}", None)
    st["macros"].pop(f"{layer}:{src}", None)
    replay_keys(kb, st)


def reset_keys(kb: Keyboard, st: dict):
    kb.reset_keys()
    st["remaps"].clear()
    st["macros"].clear()


def apply_settings(kb: Keyboard, st: dict, sleep: int, response: int, fn: bool):
    kb.set_sleep(sleep)
    kb.set_response(response)
    kb.set_fn_switch(fn)
    st["settings"] = {"sleep": sleep, "response": response, "fn": fn}


def factory_reset(kb: Keyboard, st: dict):
    kb.factory_reset()
    st.clear()
    st.update(state.default_state())
