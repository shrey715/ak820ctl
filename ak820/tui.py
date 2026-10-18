"""Full-screen Textual interface for the AK820 Max Plus."""

from __future__ import annotations

import threading

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Footer, Header, Input, Label, ProgressBar,
                             RadioButton, RadioSet, RichLog, Select, Static, Switch,
                             TabbedContent, TabPane)

from . import __version__, keys
from .cli import LINK_STATES, NAMED_COLORS, parse_color, parse_macro_events
from .protocol import DeviceError, Keyboard

LEVELS = [(str(i), i) for i in range(1, keys.MAX_LEVEL + 1)]
PHYSICAL_OPTIONS = [(f"{legend}  ({keys.code_name(code)})", code)
                    for code, legend, _, _, _ in keys.PHYSICAL_KEYS]
TARGET_OPTIONS = ([(f"key: {n}", c) for n, c in keys.HID_USAGES.items()] +
                  [(f"media: {n}", c) for n, c in keys.MEDIA_CODES.items()])
SWATCHES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "white", "off"]


class KeyCap(Static):
    """One clickable key in the keyboard grid."""

    def __init__(self, code: int, legend: str, led: int):
        width = "space" if legend == "Space" else "wide" if len(legend) > 3 else ""
        super().__init__(legend, classes=f"keycap {width}")
        self.code, self.led = code, led
        self.rgb = (0, 0, 0)

    def paint(self, rgb: tuple[int, int, int]):
        self.rgb = rgb
        r, g, b = rgb
        self.styles.background = f"rgb({r},{g},{b})"
        light = (r * 299 + g * 587 + b * 114) > 128000
        self.styles.color = "black" if light else "white"

    def on_click(self):
        self.toggle_class("selected")


class Confirm(ModalScreen[bool]):
    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.question)
            with Horizontal():
                yield Button("Cancel", id="no")
                yield Button("Yes", id="yes", variant="error")

    @on(Button.Pressed)
    def answer(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


class AK820App(App):
    TITLE = "AK820 Max Plus"
    SUB_TITLE = f"Linux driver v{__version__}"
    CSS = """
    #statusbar { height: 3; padding: 0 1; border: round $accent; }
    #statusbar Label { margin: 0 2 0 0; }
    #battery { width: 30; }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; padding: 0 1; }
    #log { height: 8; border: round $secondary; }
    .row { height: 3; }
    .keyrow { height: 3; margin: 0 0 0 0; }
    .keycap { width: 5; height: 3; content-align: center middle; margin: 0 1 0 0;
              background: #202020; }
    .keycap.wide { width: 7; }
    .keycap.space { width: 15; }
    .keycap.selected { outline: round $warning; text-style: bold underline; }
    #keyboard { height: auto; margin: 1 0; }
    .field { width: 18; padding: 1 1 0 0; }
    Select { width: 30; }
    #swatches Button { min-width: 8; width: 9; margin: 0 1 0 0; }
    #hexcolor { width: 14; }
    #settings-row { height: auto; }
    RadioSet { width: 24; margin: 1 2 1 0; }
    Button { margin: 0 1 0 0; }
    Confirm { align: center middle; }
    #dialog { width: 60; height: 9; border: thick $error; padding: 1 2; background: $surface; }
    """
    BINDINGS = [("r", "refresh_status", "Refresh status"), ("q", "quit", "Quit")]

    def __init__(self, device: str | None = None, dry_run: bool = False):
        super().__init__()
        self.device_path, self.dry_run = device, dry_run
        self.kb: Keyboard | None = None
        self.lock = threading.Lock()

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="statusbar"):
            yield Label("connecting…", id="conn")
            yield Label("Battery")
            yield ProgressBar(total=100, show_eta=False, id="battery")
            yield Label("", id="link")
        with TabbedContent():
            with TabPane("Lighting", id="tab-light"):
                with VerticalScroll():
                    yield Label("Effect")
                    yield Select([(f"{n:>2}  {name}", n) for n, (name, _) in
                                  keys.LIGHT_MODES.items()], value=7, allow_blank=False,
                                 id="mode")
                    with Horizontal(classes="row"):
                        yield Label("Brightness", classes="field")
                        yield Select(LEVELS, value=keys.DEFAULT_BRIGHTNESS,
                                     allow_blank=False, id="brightness")
                    with Horizontal(classes="row"):
                        yield Label("Speed", classes="field")
                        yield Select(LEVELS, value=keys.DEFAULT_SPEED, allow_blank=False,
                                     id="speed")
                    with Horizontal(classes="row"):
                        yield Label("Direction", classes="field")
                        yield Select([(str(i), i) for i in range(4)], value=0,
                                     allow_blank=False, id="direction")
                    with Horizontal(classes="row"):
                        yield Label("Colour index", classes="field")
                        yield Select([(str(i), i) for i in range(8)], value=0,
                                     allow_blank=False, id="colorindex")
                    yield Label("", id="mode-hint")
                    yield Button("Apply effect", id="apply-light", variant="primary")
            with TabPane("Per-key RGB", id="tab-rgb"):
                with VerticalScroll():
                    yield from self.compose_keyboard()
                    with Horizontal(id="swatches", classes="row"):
                        for name in SWATCHES:
                            yield Button(name, id=f"sw-{name}")
                        yield Input(placeholder="RRGGBB", id="hexcolor")
                    with Horizontal(classes="row"):
                        yield Button("Select all", id="sel-all")
                        yield Button("Clear selection", id="sel-none")
                        yield Button("Upload to keyboard", id="upload-rgb",
                                     variant="primary")
                    yield Label("Click keys to select them, then pick a colour.")
            with TabPane("Remap", id="tab-remap"):
                with VerticalScroll():
                    yield Label("Physical key")
                    yield Select(PHYSICAL_OPTIONS, prompt="choose key", id="remap-src")
                    yield Label("New function")
                    yield Select(TARGET_OPTIONS, prompt="choose function", id="remap-dst")
                    with Horizontal(classes="row"):
                        yield Label("Fn layer", classes="field")
                        yield Switch(id="remap-fn")
                    with Horizontal(classes="row"):
                        yield Button("Apply remap", id="apply-remap", variant="primary")
                        yield Button("Reset all keys", id="reset-keys", variant="warning")
            with TabPane("Macro", id="tab-macro"):
                with VerticalScroll():
                    yield Label("Key")
                    yield Select(PHYSICAL_OPTIONS, prompt="choose key", id="macro-src")
                    yield Label("Events: +key press, -key release, key tap, @ms delay")
                    yield Input(placeholder="+lctrl c -lctrl", id="macro-events")
                    with Horizontal(classes="row"):
                        yield Label("Repeat", classes="field")
                        yield Input("1", id="macro-repeat", type="integer")
                    with Horizontal(classes="row"):
                        yield Label("Fn layer", classes="field")
                        yield Switch(id="macro-fn")
                    yield Static(id="macro-preview")
                    yield Button("Store macro", id="apply-macro", variant="primary")
            with TabPane("Settings", id="tab-settings"):
                with Horizontal(id="settings-row"):
                    with RadioSet(id="sleep"):
                        for i, t in enumerate(["5 min", "15 min", "30 min", "never"], 1):
                            yield RadioButton(t, value=i == 1, name=str(i))
                    with RadioSet(id="response"):
                        for g in (1, 2, 3):
                            yield RadioButton(f"gear {g}", value=g == 1, name=str(g))
                    with RadioSet(id="fnswitch"):
                        yield RadioButton("normal", value=True, name="0")
                        yield RadioButton("fn", name="1")
                with Horizontal(classes="row"):
                    yield Button("Apply settings", id="apply-settings", variant="primary")
                    yield Button("Factory reset", id="factory", variant="error")
        yield RichLog(id="log", markup=True, wrap=True)
        yield Footer()

    def compose_keyboard(self) -> ComposeResult:
        rows: dict[int, list] = {}
        for code, legend, led, row, col in keys.PHYSICAL_KEYS:
            rows.setdefault(row, []).append((col, code, legend, led))
        with Vertical(id="keyboard"):
            for row in sorted(rows):
                with Horizontal(classes="keyrow"):
                    for _, code, legend, led in sorted(rows[row]):
                        yield KeyCap(code, legend, led)

    # -- lifecycle ---------------------------------------------------------

    def on_mount(self):
        self.update_mode_hint(7)
        for rid, title in (("#sleep", "Sleep after"), ("#response", "Key response"),
                           ("#fnswitch", "Fn switch")):
            self.query_one(rid, RadioSet).border_title = title
        try:
            self.kb = Keyboard(self.device_path, dry_run=self.dry_run, log=self.log_packet)
            where = "dry run, nothing is sent" if self.dry_run else self.kb.path
            self.query_one("#conn", Label).update(f"[green]●[/] {where}")
            self.action_refresh_status()
            self.set_interval(5, self.action_refresh_status)
        except DeviceError as e:
            self.query_one("#conn", Label).update("[red]● not connected[/]")
            self.log_msg(f"[red]{e}[/]")
            self.log_msg("Tip: start with [b]ak820ctl -n tui[/b] to explore in dry-run mode.")

    def on_unmount(self):
        if self.kb:
            self.kb.close()

    # -- helpers -----------------------------------------------------------

    def log_msg(self, msg: str):
        self.query_one("#log", RichLog).write(msg)

    def log_packet(self, report: bytes):
        self.call_from_thread(self.log_msg,
                              f"[dim cyan]→ {report.rstrip(bytes(1)).hex(' ')}[/]")

    @work(thread=True)
    def run_device(self, label: str, fn, *args):
        if self.kb is None:
            self.call_from_thread(self.log_msg, "[red]no device[/]")
            return
        try:
            with self.lock:
                fn(*args)
            self.call_from_thread(self.log_msg, f"[green]✓[/] {label}")
        except (DeviceError, OSError, ValueError) as e:
            self.call_from_thread(self.log_msg, f"[red]✗ {label}: {e}[/]")

    def selected_value(self, selector: str):
        value = self.query_one(selector, Select).value
        return None if value is Select.BLANK else value

    # -- status ------------------------------------------------------------

    def action_refresh_status(self):
        if self.kb and not self.dry_run:
            self.poll_status()

    @work(thread=True, exclusive=True, group="status")
    def poll_status(self):
        with self.lock:
            try:
                st = self.kb.status()
            except OSError as e:
                st = e
        self.call_from_thread(self.show_status, st)

    def show_status(self, st):
        link = self.query_one("#link", Label)
        if st is None or isinstance(st, OSError):
            link.update("[yellow]no reply[/]")
            return
        link.update(LINK_STATES.get(st.link, f"link {st.link}"))
        if st.battery is not None:
            self.query_one("#battery", ProgressBar).update(progress=st.battery)

    # -- lighting ----------------------------------------------------------

    def update_mode_hint(self, mode: int):
        name, attr = keys.LIGHT_MODES.get(mode, ("?", 0))
        used = [n for n, bit in (("brightness", keys.ATTR_BRIGHTNESS),
                                 ("speed", keys.ATTR_SPEED),
                                 ("direction", keys.ATTR_DIRECTION),
                                 ("colour", keys.ATTR_COLOR)) if attr & bit]
        hint = f"[dim]{name}: uses {', '.join(used) or 'no parameters'}[/]"
        if mode == keys.CUSTOM_MODE:
            hint += "  [yellow](edit colours in the Per-key RGB tab)[/]"
        self.query_one("#mode-hint", Label).update(hint)

    @on(Select.Changed, "#mode")
    def mode_changed(self, event: Select.Changed):
        if event.value is not Select.BLANK:
            self.update_mode_hint(event.value)

    @on(Button.Pressed, "#apply-light")
    def apply_light(self):
        mode = self.selected_value("#mode")
        args = (mode, self.selected_value("#brightness"), self.selected_value("#speed"),
                self.selected_value("#direction"), self.selected_value("#colorindex"))
        self.run_device(f"effect {mode} ({keys.LIGHT_MODES[mode][0]})",
                        self.kb.set_light if self.kb else None, *args)

    # -- per-key -----------------------------------------------------------

    def keycaps(self):
        return self.query(KeyCap)

    @on(Button.Pressed, "#swatches Button")
    def swatch(self, event: Button.Pressed):
        self.paint_selected(NAMED_COLORS[event.button.id.removeprefix("sw-")])

    @on(Input.Submitted, "#hexcolor")
    def hex_color(self, event: Input.Submitted):
        try:
            self.paint_selected(parse_color(event.value))
        except Exception as e:
            self.log_msg(f"[red]{e}[/]")

    def paint_selected(self, rgb):
        caps = [k for k in self.keycaps() if k.has_class("selected")]
        if not caps:
            self.log_msg("[yellow]select some keys first[/]")
        for k in caps:
            k.paint(rgb)

    @on(Button.Pressed, "#sel-all")
    def select_all(self):
        for k in self.keycaps():
            k.add_class("selected")

    @on(Button.Pressed, "#sel-none")
    def select_none(self):
        for k in self.keycaps():
            k.remove_class("selected")

    @on(Button.Pressed, "#upload-rgb")
    def upload_rgb(self):
        colors = {k.led: k.rgb for k in self.keycaps()}
        brightness = self.selected_value("#brightness")
        self.run_device("per-key colours stored",
                        self.kb.set_custom_colors if self.kb else None, colors, brightness)

    # -- remap / macro -----------------------------------------------------

    @on(Button.Pressed, "#apply-remap")
    def apply_remap(self):
        src, dst = self.selected_value("#remap-src"), self.selected_value("#remap-dst")
        if src is None or dst is None:
            self.log_msg("[yellow]choose a key and a function[/]")
            return
        layer = 1 if self.query_one("#remap-fn", Switch).value else 0
        self.run_device(f"{'Fn+' if layer else ''}{keys.code_name(src)} → "
                        f"{keys.code_name(dst)}", self.kb.remap if self.kb else None,
                        layer, src, dst)

    @on(Button.Pressed, "#reset-keys")
    def reset_keys(self):
        def done(yes):
            if yes:
                self.run_device("key assignments reset",
                                self.kb.reset_keys if self.kb else None)
        self.push_screen(Confirm("Reset all key assignments to default?"), done)

    def macro_events(self):
        tokens = self.query_one("#macro-events", Input).value.split()
        return parse_macro_events(tokens, 10) if tokens else []

    @on(Input.Changed, "#macro-events")
    def preview_macro(self):
        preview = self.query_one("#macro-preview", Static)
        try:
            events = self.macro_events()
        except KeyError as e:
            preview.update(Text(str(e), style="red"))
            return
        text = Text()
        for code, release, delay in events:
            text.append(f" {'↑' if release else '↓'}{keys.code_name(code)} ",
                        style="red" if release else "green")
            text.append(f"{delay}ms ", style="dim")
        preview.update(text)

    @on(Button.Pressed, "#apply-macro")
    def apply_macro(self):
        src = self.selected_value("#macro-src")
        try:
            events = self.macro_events()
            repeat = int(self.query_one("#macro-repeat", Input).value or 1)
        except (KeyError, ValueError) as e:
            self.log_msg(f"[red]{e}[/]")
            return
        if src is None or not events:
            self.log_msg("[yellow]choose a key and enter events[/]")
            return
        layer = 1 if self.query_one("#macro-fn", Switch).value else 0
        self.run_device(f"macro on {keys.code_name(src)} ({len(events)} events)",
                        self.kb.set_macro if self.kb else None, layer, src, events, repeat)

    # -- settings ----------------------------------------------------------

    def radio_value(self, selector: str) -> int:
        pressed = self.query_one(selector, RadioSet).pressed_button
        return int(pressed.name) if pressed else 1

    @on(Button.Pressed, "#apply-settings")
    def apply_settings(self):
        if self.kb is None:
            self.log_msg("[red]no device[/]")
            return
        sleep, gear = self.radio_value("#sleep"), self.radio_value("#response")
        fn = self.radio_value("#fnswitch") == 1

        def apply():
            self.kb.set_sleep(sleep)
            self.kb.set_response(gear)
            self.kb.set_fn_switch(fn)
        self.run_device(f"settings (sleep option {sleep}, gear {gear}, "
                        f"fn switch {'fn' if fn else 'normal'})", apply)

    @on(Button.Pressed, "#factory")
    def factory(self):
        def done(yes):
            if yes:
                self.run_device("factory reset", self.kb.factory_reset if self.kb else None)
        self.push_screen(Confirm("Restore factory settings? All keyboard data is erased."),
                         done)


def run(device: str | None = None, dry_run: bool = False):
    AK820App(device, dry_run).run()
