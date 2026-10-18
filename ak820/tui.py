"""Full-screen Textual interface for the AK820 Max Plus."""

from __future__ import annotations

import threading

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label, Markdown,
                             OptionList, RadioButton, RadioSet, RichLog, Select, Static,
                             Switch, TabbedContent, TabPane)
from textual.widgets.option_list import Option

from . import __version__, keys, patterns, state
from .cli import LINK_STATES, NAMED_COLORS, parse_color, parse_macro_events
from .protocol import DeviceError, Keyboard, find_interfaces

TARGET_OPTIONS = ([(f"key · {n}", c) for n, c in keys.HID_USAGES.items()] +
                  [(f"media · {n}", c) for n, c in keys.MEDIA_CODES.items()])
LEGEND_BY_CODE = {code: legend for code, legend, _, _, _ in keys.PHYSICAL_KEYS}
SWATCHES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink",
            "white", "off"]
SLEEP_LABELS = ["5 min", "15 min", "30 min", "never"]
TABS = ["tab-light", "tab-rgb", "tab-remap", "tab-macro", "tab-settings"]

HELP = f"""\
# ak820ctl {__version__}

Unofficial. The keyboard can't report its settings back, so this app shows
what it last sent (saved in `~/.config/ak820ctl`).

| key | action |
|---|---|
| `1`–`5` | switch tabs |
| `ctrl+s` | apply the current tab |
| `r` | refresh battery |
| `l` | show / hide the packet log |
| `ctrl+p` | command palette, themes |
| `q` | quit |

**Per-key RGB.** Pick a brush colour, then click or drag across keys to paint.
The *pick* tool copies a key's colour into the brush. *Select* marks keys so a
pattern only fills those. Nothing reaches the keyboard until you upload.

**Remap / macro.** Click the key you want to change on the map. Remapped keys
are tinted. Restoring a remap sends the key back to itself.
"""


def rgb_hex(rgb) -> str:
    return "{:02x}{:02x}{:02x}".format(*rgb)


def text_color(rgb) -> str:
    r, g, b = rgb
    return "black" if (r * 299 + g * 587 + b * 114) > 128000 else "white"


def key_label(layer: int, code: int) -> str:
    return f"{'Fn+' if layer else ''}{LEGEND_BY_CODE.get(code, keys.code_name(code))}"


# -- widgets ----------------------------------------------------------------

class KeyCap(Static):
    def __init__(self, code: int, legend: str, led: int):
        super().__init__(legend, classes="keycap")
        self.styles.width = patterns.key_width(legend)
        self.code, self.led = code, led
        self.rgb: tuple[int, int, int] | None = None

    @property
    def keymap(self) -> "KeyboardMap":
        return self.parent.parent

    def paint(self, rgb):
        self.rgb = tuple(rgb)
        self.styles.background = "rgb({},{},{})".format(*self.rgb)
        self.styles.color = text_color(self.rgb)

    def on_mouse_down(self, event: events.MouseDown):
        if event.button == 1:
            self.keymap.dragging = True
            self.post_message(KeyboardMap.KeyPressed(self.keymap, self, drag=False))

    def on_enter(self, event: events.Enter):
        if event.node is self and self.keymap.dragging:
            self.post_message(KeyboardMap.KeyPressed(self.keymap, self, drag=True))


class KeyboardMap(Vertical):
    """Clickable 75% layout.  Posts KeyPressed on click and while dragging."""

    class KeyPressed(Message):
        def __init__(self, keymap: "KeyboardMap", cap: KeyCap, drag: bool):
            super().__init__()
            self.keymap, self.cap, self.drag = keymap, cap, drag

        @property
        def control(self):
            return self.keymap

    def __init__(self, **kwargs):
        super().__init__(classes="keymap", **kwargs)
        self.dragging = False

    def compose(self) -> ComposeResult:
        rows: dict[int, list] = {}
        for code, legend, led, row, col in keys.PHYSICAL_KEYS:
            rows.setdefault(row, []).append((col, code, legend, led))
        for row in sorted(rows):
            with Horizontal(classes="keyrow"):
                for _, code, legend, led in sorted(rows[row]):
                    yield KeyCap(code, legend, led)

    def caps(self) -> list[KeyCap]:
        return list(self.query(KeyCap))

    def cap(self, code: int) -> KeyCap:
        return next(c for c in self.caps() if c.code == code)

    def on_mouse_up(self):
        self.dragging = False


class LevelPicker(Widget, can_focus=True):
    """Five clickable blocks; left/right arrows when focused."""

    BINDINGS = [("left", "step(-1)", "less"), ("right", "step(1)", "more")]
    value = reactive(1)

    class Changed(Message):
        def __init__(self, picker: "LevelPicker", value: int):
            super().__init__()
            self.picker, self.value = picker, value

        @property
        def control(self):
            return self.picker

    def __init__(self, value: int, **kwargs):
        super().__init__(**kwargs)
        self.set_reactive(LevelPicker.value, value)

    def render(self) -> Text:
        text = Text()
        for i in range(1, keys.MAX_LEVEL + 1):
            filled = i <= self.value
            text.append("███ " if filled else "░░░ ",
                        style="grey42" if self.disabled else
                        ("bold #f0a030" if filled else "grey35"))
        text.append(f" {self.value}/{keys.MAX_LEVEL}",
                    style="grey42" if self.disabled else "bold")
        return text

    def watch_value(self, value: int):
        self.post_message(self.Changed(self, value))

    def on_click(self, event: events.Click):
        if not self.disabled and event.x < keys.MAX_LEVEL * 4:
            self.value = event.x // 4 + 1

    def action_step(self, delta: int):
        self.value = min(max(self.value + delta, 1), keys.MAX_LEVEL)


class Swatch(Static):
    class Picked(Message):
        def __init__(self, rgb):
            super().__init__()
            self.rgb = rgb

    def __init__(self, name: str):
        super().__init__(name, classes="swatch")
        self.rgb = NAMED_COLORS[name]
        self.styles.background = "rgb({},{},{})".format(*self.rgb)
        self.styles.color = text_color(self.rgb)
        self.tooltip = f"#{rgb_hex(self.rgb)}"

    def on_click(self):
        self.post_message(self.Picked(self.rgb))


class Confirm(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "cancel")]

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.question)
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="no")
                yield Button("Yes, do it", id="yes", variant="error")

    @on(Button.Pressed)
    def answer(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


class HelpScreen(ModalScreen):
    BINDINGS = [("escape,question_mark,f1", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help"):
            yield Markdown(HELP)
            yield Label("[dim]esc to close[/]")


# -- app --------------------------------------------------------------------

class AK820App(App):
    TITLE = "AK820 Max Plus"
    SUB_TITLE = "unofficial linux driver"
    CSS = """
    Screen { background: $background; }
    #statusbar { height: 3; padding: 0 1; border: round $primary; }
    #statusbar > Static { width: auto; margin: 0 3 0 0; }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; padding: 0 1; }
    #log { height: 8; border: round $secondary; }
    #log.hidden { display: none; }

    .keymap { height: auto; width: auto; margin: 1 0; padding: 0 1;
              border: round $panel-lighten-2; }
    .keyrow { height: 3; width: auto; }
    .keycap { height: 3; content-align: center middle; margin: 0 1 0 0;
              background: #1c1c1c; color: $text-muted; }
    .keycap:hover { text-style: bold; }
    .keycap.selected { outline: round $warning; text-style: bold underline; }
    .keycap.picked { outline: heavy $success; text-style: bold; }
    .keycap.remapped { background: $secondary 60%; color: $text; }
    .keycap.has-macro { background: $accent 50%; color: $text; }

    .panel { border: round $panel-lighten-1; padding: 0 1; height: auto; }
    .row { height: auto; margin: 0 0 1 0; }
    .caption { color: $text-muted; }
    .field { width: 14; padding: 1 0 0 0; }
    LevelPicker { width: 30; height: 1; margin: 1 0 0 0; }
    LevelPicker:focus { background: $boost; }

    #light-body { height: 1fr; }
    #mode-list { width: 40; height: 1fr; border: round $panel-lighten-1; }
    #light-params { width: 1fr; padding: 0 2; }
    #mode-title { text-style: bold; color: $accent; margin: 1 0 0 0; }

    #rgb-tools { height: auto; }
    .swatch { width: 8; height: 1; content-align: center middle; margin: 0 1 0 0; }
    #brush { width: 18; height: 3; content-align: center middle; border: tall $panel; }
    #brush2 { width: 18; height: 3; content-align: center middle; border: tall $panel; }
    #hexcolor, #hexcolor2 { width: 18; margin: 0 2 0 0; }
    #tool { layout: horizontal; width: auto; height: auto; border: none; padding: 0;
            background: transparent; margin: 1 0 0 0; }
    #tool RadioButton { width: auto; margin: 0 3 0 0; background: transparent; }
    #pattern, #preset-load { width: 44; }
    #preset-name { width: 22; }
    #dirty { color: $warning; padding: 1 0 0 1; }

    #remap-side, #macro-side { width: 1fr; min-width: 34; padding: 0 1; }
    #remap-side Button, #macro-side Button { min-width: 12; }
    #remap-target { width: 40; }
    #remap-table, #macro-table { height: 10; }
    #macro-preview { height: auto; min-height: 1; margin: 1 0; }

    #settings-row { height: auto; }
    #settings-row RadioSet { width: 24; margin: 1 2 1 0; }

    Confirm, HelpScreen { align: center middle; }
    #dialog { width: 62; height: auto; border: thick $error; padding: 1 2;
              background: $surface; }
    #dialog-buttons { height: auto; margin: 1 0 0 0; align-horizontal: right; }
    #help { width: 76; height: 80%; border: thick $primary; padding: 1 2;
            background: $surface; }
    Button { margin: 0 1 0 0; }
    """
    BINDINGS = [
        Binding("ctrl+s", "apply", "Apply"),
        Binding("r", "refresh_status", "Battery"),
        Binding("l", "toggle_log", "Log"),
        Binding("question_mark,f1", "help", "Help"),
        Binding("q", "quit", "Quit"),
        *[Binding(str(i + 1), f"tab({i})", show=False) for i in range(len(TABS))],
    ]

    def __init__(self, device: str | None = None, dry_run: bool = False):
        super().__init__()
        self.device_path, self.dry_run = device, dry_run
        self.kb: Keyboard | None = None
        self.lock = threading.Lock()
        self.state = state.load()
        self.brush = (255, 255, 255)
        self.brush2 = (0, 0, 40)
        self.remap_src: int | None = None
        self.macro_src: int | None = None

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="statusbar"):
            yield Static("[yellow]●[/] connecting…", id="conn")
            yield Static("", id="battery")
            yield Static("", id="link")
        with TabbedContent():
            with TabPane("1 Lighting", id="tab-light"):
                yield from self.compose_lighting()
            with TabPane("2 Per-key RGB", id="tab-rgb"):
                yield from self.compose_rgb()
            with TabPane("3 Remap", id="tab-remap"):
                yield from self.compose_remap()
            with TabPane("4 Macro", id="tab-macro"):
                yield from self.compose_macro()
            with TabPane("5 Settings", id="tab-settings"):
                yield from self.compose_settings()
        yield RichLog(id="log", markup=True, wrap=True, classes="hidden")
        yield Footer()

    def compose_lighting(self) -> ComposeResult:
        light = self.state["light"]
        with Horizontal(id="light-body"):
            yield OptionList(*[Option(f"{n:>2}  {name}", id=str(n))
                               for n, (name, _) in keys.LIGHT_MODES.items()], id="mode-list")
            with VerticalScroll(id="light-params"):
                yield Label("", id="mode-title")
                yield Label("", id="mode-hint", classes="caption")
                with Horizontal(classes="row"):
                    yield Label("Brightness", classes="field")
                    yield LevelPicker(light["brightness"], id="brightness")
                with Horizontal(classes="row"):
                    yield Label("Speed", classes="field")
                    yield LevelPicker(light["speed"], id="speed")
                with Horizontal(classes="row"):
                    yield Label("Direction", classes="field")
                    yield Select([(f"direction {i}", i) for i in range(4)],
                                 value=light["direction"], allow_blank=False, id="direction")
                with Horizontal(classes="row"):
                    yield Label("Colour", classes="field")
                    yield Select([(f"palette index {i}", i) for i in range(9)],
                                 value=light["color"], allow_blank=False, id="colorindex")
                yield Label("[dim]palette index → colour isn't mapped yet (issue #1)[/]")
                yield Button("Apply effect", id="apply-light", variant="primary")

    def compose_rgb(self) -> ComposeResult:
        with VerticalScroll():
            yield KeyboardMap(id="rgb-map")
            with Vertical(id="rgb-tools"):
                with Horizontal(classes="row"):
                    for name in SWATCHES:
                        yield Swatch(name)
                with Horizontal(classes="row"):
                    yield Static("", id="brush")
                    yield Input(placeholder="hex, enter", id="hexcolor")
                    yield Static("", id="brush2")
                    yield Input(placeholder="hex, enter", id="hexcolor2")
                with Horizontal(classes="row"):
                    yield Label("Tool", classes="field")
                    with RadioSet(id="tool"):
                        yield RadioButton("paint", value=True, name="paint")
                        yield RadioButton("pick colour", name="pick")
                        yield RadioButton("select", name="select")
                with Horizontal(classes="row"):
                    yield Select([(desc, key) for key, desc in patterns.PATTERNS.items()],
                                 value="rainbow-horizontal", allow_blank=False, id="pattern")
                    yield Button("Fill pattern", id="fill-pattern")
                    yield Button("Clear selection", id="sel-none")
                with Horizontal(classes="row"):
                    yield Input(placeholder="preset name", id="preset-name")
                    yield Button("Save preset", id="save-preset")
                    yield Select([], prompt="load preset…", id="preset-load")
                with Horizontal(classes="row"):
                    yield Button("Upload to keyboard", id="upload-rgb", variant="primary")
                    yield Label("", id="dirty")

    def compose_remap(self) -> ComposeResult:
        with Horizontal():
            yield KeyboardMap(id="remap-map")
            with VerticalScroll(id="remap-side"):
                yield Label("[b]Key[/b]  click one on the map", id="remap-key")
                with Horizontal(classes="row"):
                    yield Label("Fn layer", classes="field")
                    yield Switch(id="remap-fn")
                yield Label("New function [dim](type to search)[/]")
                yield Select(TARGET_OPTIONS, prompt="choose…", id="remap-target")
                with Horizontal(classes="row"):
                    yield Button("Apply", id="apply-remap", variant="primary")
                    yield Button("Restore", id="restore-key")
                yield Label("[b]Your remaps[/b]")
                yield DataTable(id="remap-table", cursor_type="row")
                yield Button("Reset all keys", id="reset-keys", variant="warning")

    def compose_macro(self) -> ComposeResult:
        with Horizontal():
            yield KeyboardMap(id="macro-map")
            with VerticalScroll(id="macro-side"):
                yield Label("[b]Key[/b]  click one on the map", id="macro-key")
                with Horizontal(classes="row"):
                    yield Label("Fn layer", classes="field")
                    yield Switch(id="macro-fn")
                yield Label("Events")
                yield Label("+key press · -key release · key tap · @ms delay",
                            classes="caption")
                yield Input(placeholder="+lctrl c -lctrl", id="macro-events")
                yield Static(id="macro-preview")
                with Horizontal(classes="row"):
                    yield Label("Repeat", classes="field")
                    yield Input("1", id="macro-repeat", type="integer")
                yield Button("Store macro", id="apply-macro", variant="primary")
                yield Label("[b]Your macros[/b]")
                yield DataTable(id="macro-table", cursor_type="row")

    def compose_settings(self) -> ComposeResult:
        s = self.state["settings"]
        with Horizontal(id="settings-row"):
            with RadioSet(id="sleep"):
                for i, label in enumerate(SLEEP_LABELS, 1):
                    yield RadioButton(label, value=s["sleep"] == i, name=str(i))
            with RadioSet(id="response"):
                for g in (1, 2, 3):
                    yield RadioButton(f"gear {g}", value=s["response"] == g, name=str(g))
            with RadioSet(id="fnswitch"):
                yield RadioButton("normal", value=not s["fn"], name="0")
                yield RadioButton("fn", value=s["fn"], name="1")
        yield Label("[dim]gear 1 is the fastest response. "
                    "fn switch swaps the F-row default layer.[/]")
        with Horizontal(classes="row"):
            yield Button("Apply settings", id="apply-settings", variant="primary")
            yield Button("Factory reset", id="factory", variant="error")

    # -- lifecycle ---------------------------------------------------------

    def on_mount(self):
        for rid, title in (("#sleep", "Sleep after"), ("#response", "Key response"),
                           ("#fnswitch", "Fn switch")):
            self.query_one(rid, RadioSet).border_title = title
        self.query_one("#rgb-map", KeyboardMap).border_title = "click or drag to paint"
        self.query_one("#remap-map", KeyboardMap).border_title = "pick a key"
        self.query_one("#macro-map", KeyboardMap).border_title = "pick a key"
        self.query_one("#remap-table", DataTable).add_columns("key", "→", "function")
        self.query_one("#macro-table", DataTable).add_columns("key", "events", "repeat")

        mode_list = self.query_one("#mode-list", OptionList)
        mode_list.highlighted = mode_list.get_option_index(str(self.state["light"]["mode"]))
        self.set_brush(self.brush)
        self.set_brush2(self.brush2)
        saved = state.colors_from_json(self.state["colors"])
        for cap in self.query_one("#rgb-map", KeyboardMap).caps():
            cap.paint(saved.get(cap.led, (0, 0, 0)))
        self.refresh_presets()
        self.refresh_remaps()
        self.refresh_macros()
        self.connect()

    def connect(self):
        try:
            self.kb = Keyboard(self.device_path, dry_run=self.dry_run, log=self.log_packet)
        except DeviceError as e:
            self.query_one("#conn", Static).update("[red]●[/] not connected")
            self.log_msg(f"[red]{e}[/]")
            self.notify(str(e), title="keyboard not available", severity="error", timeout=8)
            return
        if self.dry_run:
            self.query_one("#conn", Static).update("[blue]●[/] dry run [dim](nothing is sent)[/]")
            return
        kind = next((i.connection for i in find_interfaces() if i.path == self.kb.path), "")
        self.query_one("#conn", Static).update(f"[green]●[/] {kind} [dim]{self.kb.path}[/]")
        self.action_refresh_status()
        self.set_interval(5, self.action_refresh_status)

    def on_unmount(self):
        if self.kb:
            self.kb.close()

    def on_mouse_up(self):
        for m in self.query(KeyboardMap):
            m.dragging = False

    # -- actions -----------------------------------------------------------

    def action_tab(self, index: int):
        self.query_one(TabbedContent).active = TABS[index]

    def action_toggle_log(self):
        self.query_one("#log").toggle_class("hidden")

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_apply(self):
        handler = {"tab-light": self.apply_light, "tab-rgb": self.upload_rgb,
                   "tab-remap": self.apply_remap, "tab-macro": self.apply_macro,
                   "tab-settings": self.apply_settings}
        handler[self.query_one(TabbedContent).active]()

    # -- device plumbing ---------------------------------------------------

    def log_msg(self, msg: str):
        self.query_one("#log", RichLog).write(msg)

    def log_packet(self, report: bytes):
        self.call_from_thread(self.log_msg,
                              f"[dim cyan]→ {report.rstrip(bytes(1)).hex(' ')}[/]")

    def device_call(self, label: str, fn, on_success=None):
        if self.kb is None:
            self.notify("no keyboard connected", severity="error")
            return
        self.run_device(label, fn, on_success)

    @work(thread=True)
    def run_device(self, label: str, fn, on_success):
        try:
            with self.lock:
                fn()
        except (DeviceError, OSError, ValueError) as e:
            self.call_from_thread(self.finish, label, e, None)
        else:
            self.call_from_thread(self.finish, label, None, on_success)

    def finish(self, label: str, error, on_success):
        if error:
            self.log_msg(f"[red]✗ {label}: {error}[/]")
            self.notify(f"{label}: {error}", severity="error")
            return
        self.log_msg(f"[green]✓[/] {label}")
        self.notify(label, title="sent" if not self.dry_run else "dry run", timeout=3)
        if on_success:
            on_success()
            if not self.dry_run:
                state.save(self.state)

    # -- status ------------------------------------------------------------

    def action_refresh_status(self):
        if self.kb and not self.dry_run:
            self.poll_status()

    @work(thread=True, exclusive=True, group="status")
    def poll_status(self):
        with self.lock:
            try:
                st = self.kb.status()
            except OSError:
                st = None
        self.call_from_thread(self.show_status, st)

    def show_status(self, st):
        link = self.query_one("#link", Static)
        battery = self.query_one("#battery", Static)
        if st is None:
            link.update("[yellow]no reply[/]")
            return
        icon = "⚡" if st.link == 3 else "●" if st.online else "○"
        link.update(f"{icon} {LINK_STATES.get(st.link, f'link {st.link}')}")
        if st.battery is None or not st.online:
            battery.update("")
            return
        colour = "green" if st.battery > 50 else "yellow" if st.battery > 20 else "red"
        filled = round(st.battery / 10)
        battery.update(f"battery [{colour}]{'▰' * filled}{'▱' * (10 - filled)}[/] "
                       f"[b]{st.battery}%[/]")

    # -- lighting ----------------------------------------------------------

    def current_mode(self) -> int:
        option = self.query_one("#mode-list", OptionList).highlighted_option
        return int(option.id) if option else self.state["light"]["mode"]

    @on(OptionList.OptionHighlighted, "#mode-list")
    def mode_highlighted(self):
        mode = self.current_mode()
        name, attr = keys.LIGHT_MODES.get(mode, ("?", 0))
        self.query_one("#mode-title", Label).update(f"{mode}. {name}")
        uses = {"#brightness": keys.ATTR_BRIGHTNESS, "#speed": keys.ATTR_SPEED,
                "#direction": keys.ATTR_DIRECTION, "#colorindex": keys.ATTR_COLOR}
        for selector, bit in uses.items():
            self.query_one(selector).disabled = not attr & bit
        hint = {keys.CUSTOM_MODE: "per-key colours, edit them in the Per-key RGB tab",
                22: "driven by the PC (music), not implemented yet",
                23: "driven by the PC (screen), not implemented yet"}.get(mode, "")
        self.query_one("#mode-hint", Label).update(hint)

    @on(OptionList.OptionSelected, "#mode-list")
    def mode_selected(self):
        self.apply_light()

    @on(Button.Pressed, "#apply-light")
    def apply_light(self):
        light = {"mode": self.current_mode(),
                 "brightness": self.query_one("#brightness", LevelPicker).value,
                 "speed": self.query_one("#speed", LevelPicker).value,
                 "direction": self.query_one("#direction", Select).value,
                 "color": self.query_one("#colorindex", Select).value}
        name = keys.LIGHT_MODES.get(light["mode"], ("?",))[0]
        self.device_call(f"effect: {name}",
                         lambda: self.kb.set_light(*light.values()),
                         lambda: self.state.update(light=light))

    # -- per-key -----------------------------------------------------------

    def rgb_map(self) -> KeyboardMap:
        return self.query_one("#rgb-map", KeyboardMap)

    def set_brush(self, rgb):
        self.brush = tuple(rgb)
        brush = self.query_one("#brush", Static)
        brush.styles.background = "rgb({},{},{})".format(*rgb)
        brush.styles.color = text_color(rgb)
        brush.update(f"brush #{rgb_hex(rgb)}")

    def set_brush2(self, rgb):
        self.brush2 = tuple(rgb)
        b2 = self.query_one("#brush2", Static)
        b2.styles.background = "rgb({},{},{})".format(*rgb)
        b2.styles.color = text_color(rgb)
        b2.update(f"second #{rgb_hex(rgb)}")

    def mark_dirty(self, dirty: bool = True):
        self.query_one("#dirty", Label).update("● unsaved changes" if dirty else "")

    def tool(self) -> str:
        pressed = self.query_one("#tool", RadioSet).pressed_button
        return pressed.name if pressed else "paint"

    @on(Swatch.Picked)
    def swatch_picked(self, event: Swatch.Picked):
        self.set_brush(event.rgb)

    @on(Input.Submitted, "#hexcolor")
    @on(Input.Submitted, "#hexcolor2")
    def hex_submitted(self, event: Input.Submitted):
        try:
            rgb = parse_color(event.value)
        except Exception as e:
            self.notify(str(e), severity="error")
            return
        (self.set_brush if event.input.id == "hexcolor" else self.set_brush2)(rgb)

    @on(KeyboardMap.KeyPressed, "#rgb-map")
    def rgb_key(self, event: KeyboardMap.KeyPressed):
        tool = self.tool()
        if tool == "paint":
            event.cap.paint(self.brush)
            self.mark_dirty()
        elif tool == "pick" and not event.drag:
            self.set_brush(event.cap.rgb or (0, 0, 0))
            self.query_one("#tool", RadioSet).query(RadioButton).first().value = True
        elif tool == "select":
            event.cap.toggle_class("selected")

    @on(Button.Pressed, "#sel-none")
    def select_none(self):
        for cap in self.rgb_map().caps():
            cap.remove_class("selected")

    @on(Button.Pressed, "#fill-pattern")
    def fill_pattern(self):
        colours = patterns.generate(self.query_one("#pattern", Select).value,
                                    self.brush, self.brush2)
        caps = self.rgb_map().caps()
        targets = [c for c in caps if c.has_class("selected")] or caps
        for cap in targets:
            cap.paint(colours[cap.led])
        self.mark_dirty()

    def current_colors(self) -> state.Colors:
        return {cap.led: cap.rgb or (0, 0, 0) for cap in self.rgb_map().caps()}

    @on(Button.Pressed, "#upload-rgb")
    def upload_rgb(self):
        colors = self.current_colors()
        brightness = self.state["light"]["brightness"]

        def saved():
            self.state["colors"] = state.colors_to_json(colors)
            self.state["light"]["mode"] = keys.CUSTOM_MODE
            self.mark_dirty(False)
        self.device_call("per-key colours uploaded",
                         lambda: self.kb.set_custom_colors(colors, brightness), saved)

    def refresh_presets(self):
        self.query_one("#preset-load", Select).set_options(
            [(name, name) for name in state.list_presets()])

    @on(Button.Pressed, "#save-preset")
    def save_preset(self):
        name = self.query_one("#preset-name", Input).value
        try:
            slug = state.save_preset(name, self.current_colors())
        except (OSError, ValueError) as e:
            self.notify(str(e), severity="error")
            return
        self.refresh_presets()
        self.notify(f"saved preset '{slug}'")

    @on(Select.Changed, "#preset-load")
    def load_preset(self, event: Select.Changed):
        if event.value is Select.NULL:
            return
        try:
            colors = state.load_preset(event.value)
        except (OSError, ValueError) as e:
            self.notify(str(e), severity="error")
            return
        for cap in self.rgb_map().caps():
            cap.paint(colors.get(cap.led, (0, 0, 0)))
        self.mark_dirty()
        self.notify(f"loaded '{event.value}', upload to send it")

    # -- remap -------------------------------------------------------------

    def remap_layer(self) -> int:
        return 1 if self.query_one("#remap-fn", Switch).value else 0

    def refresh_remaps(self):
        layer = self.remap_layer()
        table = self.query_one("#remap-table", DataTable)
        table.clear()
        remapped = set()
        for key, dst in sorted(self.state["remaps"].items()):
            lay, src = map(int, key.split(":"))
            table.add_row(key_label(lay, src), "→", keys.code_name(dst), key=key)
            if lay == layer:
                remapped.add(src)
        for cap in self.query_one("#remap-map", KeyboardMap).caps():
            cap.set_class(cap.code in remapped, "remapped")
            cap.set_class(cap.code == self.remap_src, "picked")

    @on(Switch.Changed, "#remap-fn")
    def remap_layer_changed(self):
        self.refresh_remaps()

    @on(KeyboardMap.KeyPressed, "#remap-map")
    def remap_key(self, event: KeyboardMap.KeyPressed):
        if event.drag:
            return
        self.remap_src = event.cap.code
        current = self.state["remaps"].get(f"{self.remap_layer()}:{self.remap_src}")
        extra = f"  [dim]now → {keys.code_name(current)}[/]" if current is not None else ""
        self.query_one("#remap-key", Label).update(
            f"[b]Key[/b]  {key_label(self.remap_layer(), self.remap_src)}{extra}")
        self.refresh_remaps()

    @on(DataTable.RowSelected, "#remap-table")
    def remap_row(self, event: DataTable.RowSelected):
        layer, src = map(int, event.row_key.value.split(":"))
        self.query_one("#remap-fn", Switch).value = bool(layer)
        self.remap_src = src
        self.refresh_remaps()

    @on(Button.Pressed, "#apply-remap")
    def apply_remap(self):
        dst = self.query_one("#remap-target", Select).value
        if self.remap_src is None or dst is Select.NULL:
            self.notify("pick a key on the map and a function", severity="warning")
            return
        layer, src = self.remap_layer(), self.remap_src

        def saved():
            self.state["remaps"][f"{layer}:{src}"] = dst
            self.refresh_remaps()
        self.device_call(f"{key_label(layer, src)} → {keys.code_name(dst)}",
                         lambda: self.kb.remap(layer, src, dst), saved)

    @on(Button.Pressed, "#restore-key")
    def restore_key(self):
        if self.remap_src is None:
            self.notify("pick a key first", severity="warning")
            return
        layer, src = self.remap_layer(), self.remap_src

        def saved():
            self.state["remaps"].pop(f"{layer}:{src}", None)
            self.refresh_remaps()
        self.device_call(f"{key_label(layer, src)} restored",
                         lambda: self.kb.remap(layer, src, src), saved)

    @on(Button.Pressed, "#reset-keys")
    def reset_keys(self):
        def saved():
            self.state["remaps"].clear()
            self.state["macros"].clear()
            self.refresh_remaps()
            self.refresh_macros()

        def done(yes):
            if yes:
                self.device_call("all keys reset", lambda: self.kb.reset_keys(), saved)
        self.push_screen(Confirm("Reset every remap and macro back to default?"), done)

    # -- macro -------------------------------------------------------------

    def macro_layer(self) -> int:
        return 1 if self.query_one("#macro-fn", Switch).value else 0

    def refresh_macros(self):
        layer = self.macro_layer()
        table = self.query_one("#macro-table", DataTable)
        table.clear()
        with_macro = set()
        for key, m in sorted(self.state["macros"].items()):
            lay, src = map(int, key.split(":"))
            table.add_row(key_label(lay, src), m["events"], f"×{m['repeat']}", key=key)
            if lay == layer:
                with_macro.add(src)
        for cap in self.query_one("#macro-map", KeyboardMap).caps():
            cap.set_class(cap.code in with_macro, "has-macro")
            cap.set_class(cap.code == self.macro_src, "picked")

    @on(Switch.Changed, "#macro-fn")
    def macro_layer_changed(self):
        self.refresh_macros()

    @on(KeyboardMap.KeyPressed, "#macro-map")
    def macro_key(self, event: KeyboardMap.KeyPressed):
        if event.drag:
            return
        self.macro_src = event.cap.code
        self.query_one("#macro-key", Label).update(
            f"[b]Key[/b]  {key_label(self.macro_layer(), self.macro_src)}")
        existing = self.state["macros"].get(f"{self.macro_layer()}:{self.macro_src}")
        if existing:
            self.query_one("#macro-events", Input).value = existing["events"]
            self.query_one("#macro-repeat", Input).value = str(existing["repeat"])
        self.refresh_macros()

    def macro_events(self):
        tokens = self.query_one("#macro-events", Input).value.split()
        return parse_macro_events(tokens, 10) if tokens else []

    @on(Input.Changed, "#macro-events")
    def preview_macro(self):
        preview = self.query_one("#macro-preview", Static)
        try:
            events_ = self.macro_events()
        except KeyError as e:
            preview.update(Text(str(e), style="red"))
            return
        text = Text()
        for code, release, delay in events_:
            text.append(f" {'↑' if release else '↓'} {keys.code_name(code)} ",
                        style="black on #e06c75" if release else "black on #98c379")
            text.append(f" {delay}ms  ", style="dim")
        preview.update(text)

    @on(Button.Pressed, "#apply-macro")
    def apply_macro(self):
        raw = self.query_one("#macro-events", Input).value.strip()
        try:
            events_ = self.macro_events()
            repeat = int(self.query_one("#macro-repeat", Input).value or 1)
        except (KeyError, ValueError) as e:
            self.notify(str(e), severity="error")
            return
        if self.macro_src is None or not events_:
            self.notify("pick a key on the map and enter some events", severity="warning")
            return
        layer, src = self.macro_layer(), self.macro_src

        def saved():
            self.state["macros"][f"{layer}:{src}"] = {"events": raw, "repeat": repeat}
            self.refresh_macros()
        self.device_call(f"macro on {key_label(layer, src)} ({len(events_)} events)",
                         lambda: self.kb.set_macro(layer, src, events_, repeat), saved)

    # -- settings ----------------------------------------------------------

    def radio_value(self, selector: str) -> int:
        pressed = self.query_one(selector, RadioSet).pressed_button
        return int(pressed.name) if pressed else 1

    @on(Button.Pressed, "#apply-settings")
    def apply_settings(self):
        settings = {"sleep": self.radio_value("#sleep"),
                    "response": self.radio_value("#response"),
                    "fn": self.radio_value("#fnswitch") == 1}

        def send():
            self.kb.set_sleep(settings["sleep"])
            self.kb.set_response(settings["response"])
            self.kb.set_fn_switch(settings["fn"])
        self.device_call(f"settings: sleep {SLEEP_LABELS[settings['sleep'] - 1]}, "
                         f"gear {settings['response']}, "
                         f"fn {'on' if settings['fn'] else 'off'}",
                         send, lambda: self.state.update(settings=settings))

    @on(Button.Pressed, "#factory")
    def factory(self):
        def saved():
            self.state.update(state.default_state())
            self.refresh_remaps()
            self.refresh_macros()

        def done(yes):
            if yes:
                self.device_call("factory reset", lambda: self.kb.factory_reset(), saved)
        self.push_screen(Confirm("Restore factory settings? Everything stored on the "
                                 "keyboard gets erased."), done)


def run(device: str | None = None, dry_run: bool = False):
    AK820App(device, dry_run).run()
