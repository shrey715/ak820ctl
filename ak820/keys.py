"""Key, LED and lighting tables recovered from the vendor driver package.

Sources (vendor installer v1.0.4.6):
  * PHYSICAL_KEYS / lighting modes: layouts/kb-k600t.xml
  * MEDIA codes: XYUI.dll  KeyFuncControl::InitItemInfo item data
  * HID usages: USB HID Usage Tables, keyboard page (0x07)
"""

# HID keyboard-page usages, canonical lowercase names.
HID_USAGES = {
    **{chr(ord("a") + i): 0x04 + i for i in range(26)},
    **{str((i + 1) % 10): 0x1E + i for i in range(10)},
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "lbracket": 0x2F, "rbracket": 0x30,
    "backslash": 0x31, "semicolon": 0x33, "quote": 0x34, "grave": 0x35,
    "comma": 0x36, "period": 0x37, "slash": 0x38, "capslock": 0x39,
    **{f"f{i}": 0x3A + i - 1 for i in range(1, 13)},
    **{f"f{i}": 0x68 + i - 13 for i in range(13, 25)},
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49,
    "home": 0x4A, "pageup": 0x4B, "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "numlock": 0x53,
    "kp_slash": 0x54, "kp_asterisk": 0x55, "kp_minus": 0x56, "kp_plus": 0x57,
    "kp_enter": 0x58, **{f"kp{(i + 1) % 10}": 0x59 + i for i in range(10)},
    "kp_dot": 0x63, "app": 0x65,
    "lctrl": 0xE0, "lshift": 0xE1, "lalt": 0xE2, "lwin": 0xE3,
    "rctrl": 0xE4, "rshift": 0xE5, "ralt": 0xE6, "rwin": 0xE7,
}

ALIASES = {
    "escape": "esc", "return": "enter", "del": "delete", "ins": "insert",
    "pgup": "pageup", "pgdn": "pagedown", "caps": "capslock", "bksp": "backspace",
    "ctrl": "lctrl", "shift": "lshift", "alt": "lalt", "win": "lwin",
    "super": "lwin", "meta": "lwin", "menu": "app", "`": "grave", "-": "minus",
    "=": "equal", "[": "lbracket", "]": "rbracket", "\\": "backslash",
    ";": "semicolon", "'": "quote", ",": "comma", ".": "period", "/": "slash",
}

# Single-byte "multimedia" function codes understood by the firmware
# (XYUI.dll KeyFuncControl item data, observed 0xE8..0xF9).
MEDIA_CODES = {
    "media": 0xE8, "voldown": 0xE9, "volup": 0xEA, "mute": 0xEB, "stop": 0xEC,
    "prev": 0xED, "playpause": 0xEE, "next": 0xEF, "email": 0xF0,
    "www_home": 0xF1, "calculator": 0xF2, "www_back": 0xF3, "www_forward": 0xF4,
    "www_stop": 0xF5, "www_refresh": 0xF6, "www_search": 0xF7,
    "www_favorites": 0xF8, "mycomputer": 0xF9,
}

FN_CODE = 0xAF  # vendor code for the Fn key in the layout file

# (hid code, legend, led/matrix index, row, column) for the 82 physical keys.
PHYSICAL_KEYS = [
    (0x29, "Esc", 15, 0, 0), (0x3A, "F1", 14, 0, 1), (0x3B, "F2", 13, 0, 2),
    (0x3C, "F3", 12, 0, 3), (0x3D, "F4", 11, 0, 4), (0x3E, "F5", 10, 0, 5),
    (0x3F, "F6", 9, 0, 6), (0x40, "F7", 8, 0, 7), (0x41, "F8", 7, 0, 8),
    (0x42, "F9", 6, 0, 9), (0x43, "F10", 5, 0, 10), (0x44, "F11", 4, 0, 11),
    (0x45, "F12", 3, 0, 12), (0x4C, "Del", 43, 0, 13),
    (0x35, "`", 16, 1, 0), (0x1E, "1", 17, 1, 1), (0x1F, "2", 18, 1, 2),
    (0x20, "3", 19, 1, 3), (0x21, "4", 20, 1, 4), (0x22, "5", 21, 1, 5),
    (0x23, "6", 22, 1, 6), (0x24, "7", 23, 1, 7), (0x25, "8", 24, 1, 8),
    (0x26, "9", 25, 1, 9), (0x27, "0", 26, 1, 10), (0x2D, "-", 27, 1, 11),
    (0x2E, "=", 28, 1, 12), (0x2A, "Bksp", 29, 1, 13), (0x4A, "Home", 31, 1, 14),
    (0x2B, "Tab", 57, 2, 0), (0x14, "Q", 56, 2, 1), (0x1A, "W", 55, 2, 2),
    (0x08, "E", 54, 2, 3), (0x15, "R", 53, 2, 4), (0x17, "T", 52, 2, 5),
    (0x1C, "Y", 51, 2, 6), (0x18, "U", 50, 2, 7), (0x0C, "I", 49, 2, 8),
    (0x12, "O", 48, 2, 9), (0x13, "P", 47, 2, 10), (0x2F, "[", 46, 2, 11),
    (0x30, "]", 45, 2, 12), (0x31, "\\", 44, 2, 13), (0x4B, "PgUp", 32, 2, 14),
    (0x39, "Caps", 58, 3, 0), (0x04, "A", 59, 3, 1), (0x16, "S", 60, 3, 2),
    (0x07, "D", 61, 3, 3), (0x09, "F", 62, 3, 4), (0x0A, "G", 63, 3, 5),
    (0x0B, "H", 64, 3, 6), (0x0D, "J", 65, 3, 7), (0x0E, "K", 66, 3, 8),
    (0x0F, "L", 67, 3, 9), (0x33, ";", 68, 3, 10), (0x34, "'", 69, 3, 11),
    (0x28, "Enter", 70, 3, 12), (0x4E, "PgDn", 41, 3, 13),
    (0xE1, "Shift", 90, 4, 0), (0x1D, "Z", 89, 4, 1), (0x1B, "X", 88, 4, 2),
    (0x06, "C", 87, 4, 3), (0x19, "V", 86, 4, 4), (0x05, "B", 85, 4, 5),
    (0x11, "N", 84, 4, 6), (0x10, "M", 83, 4, 7), (0x36, ",", 82, 4, 8),
    (0x37, ".", 81, 4, 9), (0x38, "/", 80, 4, 10), (0xE5, "Shift", 79, 4, 11),
    (0x52, "↑", 78, 4, 12), (0x4D, "End", 42, 4, 13),
    (0xE0, "Ctrl", 91, 5, 0), (0xE3, "Win", 92, 5, 1), (0xE2, "Alt", 93, 5, 2),
    (0x2C, "Space", 94, 5, 3), (0xE6, "Alt", 95, 5, 4), (FN_CODE, "Fn", 97, 5, 5),
    (0xE4, "Ctrl", 98, 5, 6), (0x50, "←", 99, 5, 7), (0x51, "↓", 100, 5, 8),
    (0x4F, "→", 101, 5, 9),
]

LED_BY_CODE = {code: led for code, _, led, _, _ in PHYSICAL_KEYS}

# Vendor UI rectangles (x, y, w, h on an 800x300 canvas), keyed by LED index.
KEY_RECTS = {
    15: (29, 41, 34, 34), 14: (71, 41, 34, 34), 13: (103, 41, 34, 34), 12: (136, 41, 34, 34),
    11: (169, 41, 34, 34), 10: (210, 41, 34, 34), 9: (243, 41, 34, 34), 8: (276, 41, 34, 34),
    7: (307, 41, 34, 34), 6: (350, 41, 34, 34), 5: (383, 41, 34, 34), 4: (416, 41, 34, 34),
    3: (448, 41, 34, 34), 43: (489, 41, 34, 34), 16: (30, 81, 34, 34), 17: (63, 81, 34, 34),
    18: (95, 81, 34, 34), 19: (128, 81, 34, 34), 20: (161, 81, 34, 34), 21: (194, 81, 34, 34),
    22: (227, 81, 34, 34), 23: (260, 81, 34, 34), 24: (292, 81, 34, 34), 25: (325, 81, 34, 34),
    26: (358, 81, 34, 34), 27: (390, 81, 34, 34), 28: (424, 81, 34, 34), 29: (457, 81, 65, 34),
    31: (537, 81, 34, 34), 57: (30, 114, 51, 34), 56: (79, 114, 34, 34), 55: (112, 114, 34, 34),
    54: (144, 114, 34, 34), 53: (177, 114, 34, 34), 52: (210, 114, 34, 34),
    51: (243, 114, 34, 34), 50: (276, 114, 34, 34), 49: (309, 114, 34, 34),
    48: (341, 114, 34, 34), 47: (375, 114, 34, 34), 46: (407, 114, 34, 34),
    45: (439, 114, 34, 34), 44: (473, 114, 51, 34), 32: (537, 114, 34, 34),
    58: (30, 148, 54, 34), 59: (88, 148, 34, 34), 60: (120, 148, 34, 34), 61: (153, 148, 34, 34),
    62: (186, 148, 34, 34), 63: (219, 148, 34, 34), 64: (252, 148, 34, 34),
    65: (284, 148, 34, 34), 66: (317, 148, 34, 34), 67: (351, 148, 34, 34),
    68: (383, 148, 34, 34), 69: (416, 148, 34, 34), 70: (449, 148, 74, 34),
    41: (537, 146, 34, 34), 90: (30, 180, 74, 34), 89: (103, 180, 34, 34),
    88: (137, 180, 34, 34), 87: (169, 180, 34, 34), 86: (202, 180, 34, 34),
    85: (235, 180, 34, 34), 84: (267, 180, 34, 34), 83: (300, 180, 34, 34),
    82: (333, 180, 34, 34), 81: (366, 180, 34, 34), 80: (399, 180, 34, 34),
    79: (432, 180, 54, 34), 78: (497, 186, 34, 34), 42: (537, 180, 34, 34),
    91: (31, 212, 42, 34), 92: (71, 212, 42, 34), 93: (111, 212, 42, 34),
    94: (153, 212, 208, 34), 95: (357, 212, 34, 34), 97: (390, 212, 34, 34),
    98: (424, 212, 34, 34), 99: (464, 220, 31, 34), 100: (496, 220, 31, 34),
    101: (530, 220, 31, 34),
}

# Lighting modes enabled in kb-k600t.xml.  attribute bits: 1 brightness,
# 2 speed, 4 direction, 64 colour, 256 custom per-key, 512/1024 host-driven.
ATTR_BRIGHTNESS, ATTR_SPEED, ATTR_DIRECTION, ATTR_COLOR = 1, 2, 4, 64
LIGHT_MODES = {
    1: ("Left and right ripples", 71), 2: ("Starry dots", 3),
    3: ("Up and down ripples", 71), 4: ("Bidirectional ejection", 67),
    5: ("Spectral cycle", 3), 6: ("Kaleidoscope", 71),
    7: ("Static constant light", 65), 8: ("Overall breathing", 67),
    9: ("Cross operation", 71), 11: ("Single key breathing", 67),
    12: ("Jiangshan picture scroll", 67), 15: ("Top three, bottom three", 67),
    16: ("Rain falling pavilion", 67), 17: ("Windmill", 67),
    18: ("Sine wave", 67), 19: ("Galloping horse", 71),
    22: ("Music rhythm (host driven)", 512), 23: ("Screen rhythm (host driven)", 1024),
    24: ("Custom per-key", 256),
}
# Short names for the CLI (same slugs as prasoondev/ajazz-linux).
EFFECT_SLUGS = {
    "ripple-lr": 1, "starry": 2, "ripple-ud": 3, "ejection": 4, "spectrum": 5,
    "kaleidoscope": 6, "static": 7, "breathing": 8, "cross": 9, "key-breathing": 11,
    "scroll": 12, "top-bottom": 15, "rain": 16, "windmill": 17, "sine": 18,
    "galloping": 19, "music": 22, "screen": 23, "custom": 24,
}
SLUG_BY_MODE = {mode: slug for slug, mode in EFFECT_SLUGS.items()}
CUSTOM_MODE, MUSIC_MODE, SCREEN_MODE = 24, 22, 23
DEFAULT_BRIGHTNESS, DEFAULT_SPEED, MAX_LEVEL = 5, 4, 5

# Fixed effect palette, colorindex 0..7 (vendor buttons 0x58..0x5F).
# Confirmed on hardware by prasoondev/ajazz-linux.
PALETTE = [
    ("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)),
    ("yellow", (255, 255, 0)), ("magenta", (255, 0, 255)), ("cyan", (0, 255, 255)),
    ("white", (255, 255, 255)), ("rainbow", None),
]
PALETTE_INDEX = {name: i for i, (name, _) in enumerate(PALETTE)}
RAINBOW = PALETTE_INDEX["rainbow"]
DIRECTIONS = {"left-to-right": 0, "right-to-left": 1}  # hardware-verified

# Status reply byte 6 (hardware-verified by prasoondev/ajazz-linux).
POWER_STATES = {0: "no keyboard / no data", 1: "charging", 2: "on battery",
                3: "fully charged"}


def effect_mode(name: str) -> int:
    """Lighting mode from a slug ('breathing'), a number ('8') or a name prefix."""
    n = name.strip().lower()
    if n.isdigit():
        return int(n)
    if n in EFFECT_SLUGS:
        return EFFECT_SLUGS[n]
    hits = [m for m, (title, _) in LIGHT_MODES.items() if title.lower().startswith(n)]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f"unknown effect '{name}' (try `ak820ctl modes`)")


def palette_index(name: str) -> int:
    n = name.strip().lower()
    if n.isdigit() and int(n) < len(PALETTE):
        return int(n)
    if n in PALETTE_INDEX:
        return PALETTE_INDEX[n]
    raise KeyError(f"unknown palette colour '{name}' "
                   f"({', '.join(PALETTE_INDEX)})")


def direction_value(name: str) -> int:
    n = name.strip().lower()
    aliases = {"0": 0, "1": 1, "ltr": 0, "rtl": 1, "right": 0, "left": 1,
               "left-to-right": 0, "right-to-left": 1}
    if n not in aliases:
        raise KeyError(f"unknown direction '{name}' (left-to-right / right-to-left)")
    return aliases[n]


def _norm(name: str) -> str:
    n = name.strip().lower()
    return ALIASES.get(n, n)


def key_code(name: str) -> int:
    """Physical key / HID usage from a name ('a', 'f5', 'lctrl') or hex ('0x29')."""
    if name.lower().startswith("0x"):
        return int(name, 16)
    n = _norm(name)
    if n == "fn":
        return FN_CODE
    if n in HID_USAGES:
        return HID_USAGES[n]
    raise KeyError(f"unknown key '{name}'")


def target_code(name: str) -> int:
    """Remap target: a HID key name, a media function name, or hex."""
    n = _norm(name)
    if n in MEDIA_CODES:
        return MEDIA_CODES[n]
    return key_code(name)


def code_name(code: int) -> str:
    for table in (HID_USAGES, MEDIA_CODES):
        for name, c in table.items():
            if c == code:
                return name
    return "fn" if code == FN_CODE else f"0x{code:02x}"
