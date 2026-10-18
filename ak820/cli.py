"""Command-line front end (rich-formatted) for the AK820 Max Plus driver."""

from __future__ import annotations

import argparse
import sys

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from . import __version__, keys
from .protocol import DeviceError, Keyboard, find_interfaces

console = Console()

NAMED_COLORS = {
    "off": (0, 0, 0), "black": (0, 0, 0), "white": (255, 255, 255),
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "magenta": (255, 0, 255),
    "purple": (128, 0, 255), "orange": (255, 128, 0), "pink": (255, 105, 180),
}
SLEEP_OPTIONS = {"5": 1, "15": 2, "30": 3, "never": 4}
LINK_STATES = {0: "keyboard not linked", 1: "online (on battery)", 3: "online (charging)"}


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.strip().lower()
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    h = s.lstrip("#")
    if len(h) != 6:
        raise argparse.ArgumentTypeError(f"bad colour '{s}' (use RRGGBB or a name)")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# -- rendering --------------------------------------------------------------

def render_keyboard(colors: dict[int, tuple[int, int, int]] | None = None,
                    highlight: set[int] | None = None) -> Panel:
    """Draw the 75% layout; keys tinted by LED colour or highlighted by code."""
    rows: dict[int, list] = {}
    for code, legend, led, row, col in keys.PHYSICAL_KEYS:
        rows.setdefault(row, []).append((col, code, legend, led))
    lines = []
    for row in sorted(rows):
        line = Text()
        for _, code, legend, led in sorted(rows[row]):
            width = 9 if legend == "Space" else 6 if len(legend) > 3 else 4
            label = f"{legend:^{width}}"
            if colors is not None:
                r, g, b = colors.get(led, (0, 0, 0))
                fg = "black" if (r * 299 + g * 587 + b * 114) > 128000 else "white"
                style = f"{fg} on rgb({r},{g},{b})"
            elif highlight and code in highlight:
                style = "bold black on bright_yellow"
            else:
                style = "white on grey23"
            line.append(label, style=style)
            line.append(" ")
        lines.append(line)
    return Panel(Group(*lines), title="AK820 Max Plus", box=box.ROUNDED, expand=False)


def packet_logger(report: bytes):
    console.print(Text("→ " + report.rstrip(b"\x00").hex(" "), style="dim cyan"))


def ok(msg: str):
    console.print(f"[bold green]✓[/] {msg}")


def open_keyboard(args) -> Keyboard:
    return Keyboard(args.device, dry_run=args.dry_run,
                    log=packet_logger if (args.verbose or args.dry_run) else None)


# -- commands ---------------------------------------------------------------

def cmd_devices(args):
    table = Table(title="Detected AK820 interfaces", box=box.SIMPLE_HEAVY)
    for col in ("hidraw", "connection", "usb interface", "role"):
        table.add_column(col)
    for i in find_interfaces():
        table.add_row(i.path, i.connection, i.interface,
                      "[bold green]control[/]" if i.is_control else "[dim]input[/]")
    if not table.rows:
        console.print("[red]No AK820 Max Plus found.[/] Is the cable or dongle plugged in?")
    else:
        console.print(table)


def show_status(kb: Keyboard):
    st = kb.status()
    if st is None:
        console.print(Panel("[red]No reply to status query[/]", title=kb.path))
        return
    rows = [Text.assemble(("Link:    ", "bold"),
                          LINK_STATES.get(st.link, f"unknown ({st.link})"))]
    if st.online and st.battery is not None:
        colour = "green" if st.battery > 50 else "yellow" if st.battery > 20 else "red"
        rows.append(Text.assemble(("Battery: ", "bold"), (f"{st.battery:3d}%", colour)))
        rows.append(ProgressBar(total=100, completed=st.battery, width=30,
                                complete_style=colour))
    console.print(Panel(Group(*rows), title=f"Status · {kb.path}", expand=False))


def cmd_status(args):
    with open_keyboard(args) as kb:
        show_status(kb)


def cmd_modes(args):
    table = Table(title="Lighting modes", box=box.SIMPLE_HEAVY)
    for col in ("#", "name", "brightness", "speed", "direction", "colour"):
        table.add_column(col, justify="center" if col != "name" else "left")
    tick = lambda attr, bit: "[green]●[/]" if attr & bit else "[dim]·[/]"
    for num, (name, attr) in keys.LIGHT_MODES.items():
        table.add_row(str(num), name, tick(attr, keys.ATTR_BRIGHTNESS),
                      tick(attr, keys.ATTR_SPEED), tick(attr, keys.ATTR_DIRECTION),
                      tick(attr, keys.ATTR_COLOR))
    console.print(table)


def cmd_light(args):
    if args.mode not in keys.LIGHT_MODES:
        console.print(f"[yellow]Mode {args.mode} is not listed by the vendor layout; "
                      "sending anyway.[/]")
    with open_keyboard(args) as kb:
        kb.set_light(args.mode, args.brightness, args.speed, args.direction, args.color)
    name = keys.LIGHT_MODES.get(args.mode, ("?", 0))[0]
    ok(f"mode {args.mode} ({name}), brightness {args.brightness}, speed {args.speed}, "
       f"direction {args.direction}, colour index {args.color}")


def build_colors(args) -> dict[int, tuple[int, int, int]]:
    colors = {}
    if args.all:
        colors = {led: args.all for _, _, led, _, _ in keys.PHYSICAL_KEYS}
    for spec in args.keys:
        name, _, col = spec.partition("=")
        code = keys.key_code(name)
        if code not in keys.LED_BY_CODE:
            raise KeyError(f"'{name}' is not a key on this keyboard")
        colors[keys.LED_BY_CODE[code]] = parse_color(col)
    return colors


def cmd_custom(args):
    colors = build_colors(args)
    console.print(render_keyboard(colors))
    with open_keyboard(args) as kb:
        kb.set_custom_colors(colors, args.brightness)
    ok(f"custom per-key colours stored ({len(colors)} keys)")


def cmd_frame(args):
    colors = build_colors(args)
    console.print(render_keyboard(colors))
    with open_keyboard(args) as kb:
        kb.send_frame(colors)
    ok("live frame sent (experimental, not persisted)")


def cmd_sleep(args):
    with open_keyboard(args) as kb:
        kb.set_sleep(SLEEP_OPTIONS[args.minutes])
    ok(f"sleep timer: {args.minutes}{'' if args.minutes == 'never' else ' min'}")


def cmd_response(args):
    with open_keyboard(args) as kb:
        kb.set_response(args.gear)
    ok(f"key response time: gear {args.gear}")


def cmd_fn_switch(args):
    with open_keyboard(args) as kb:
        kb.set_fn_switch(args.mode == "fn")
    ok(f"Fn switch: {args.mode}")


def cmd_remap(args):
    if args.list_targets:
        table = Table(title="Remap targets", box=box.SIMPLE)
        table.add_column("keys (HID)")
        table.add_column("media")
        table.add_row(", ".join(sorted(keys.HID_USAGES)), ", ".join(keys.MEDIA_CODES))
        console.print(table)
        return
    if not (args.src and args.dst):
        raise SystemExit("remap needs SRC and DST (or --list-targets)")
    src, dst = keys.key_code(args.src), keys.target_code(args.dst)
    console.print(render_keyboard(highlight={src}))
    with open_keyboard(args) as kb:
        kb.remap(1 if args.fn else 0, src, dst)
    ok(f"{'Fn+' if args.fn else ''}{keys.code_name(src)} → {keys.code_name(dst)}")


def parse_macro_events(tokens: list[str], default_delay: int):
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


def cmd_macro(args):
    src = keys.key_code(args.src)
    if not args.events:
        raise ValueError("macro needs at least one event")
    events = parse_macro_events(args.events, args.delay)
    table = Table(title=f"Macro on {'Fn+' if args.fn else ''}{keys.code_name(src)} "
                        f"(repeat ×{args.repeat})", box=box.SIMPLE)
    for col in ("#", "key", "action", "delay"):
        table.add_column(col)
    for i, (code, release, delay) in enumerate(events, 1):
        table.add_row(str(i), keys.code_name(code),
                      "[red]release[/]" if release else "[green]press[/]", f"{delay} ms")
    console.print(table)
    with open_keyboard(args) as kb:
        kb.set_macro(1 if args.fn else 0, src, events, args.repeat)
    ok("macro stored")


def cmd_reset_keys(args):
    with open_keyboard(args) as kb:
        kb.reset_keys()
    ok("key assignments reset to default")


def cmd_factory_reset(args):
    if not (args.yes or Confirm.ask("[red]Restore factory settings? All keyboard "
                                    "data will be erased[/]", default=False)):
        return
    with open_keyboard(args) as kb:
        kb.factory_reset()
    ok("factory reset sent")


def cmd_raw(args):
    data = bytes.fromhex("".join(args.hex))
    with open_keyboard(args) as kb:
        resp = kb.raw(data, reply=args.reply)
    if args.reply:
        console.print(resp.hex(" ") if resp else "[yellow]no reply[/]")


# -- interactive menu -------------------------------------------------------

def interactive(args):
    console.print(Panel.fit(f"[bold]AK820 Max Plus[/] Linux driver v{__version__}\n"
                            "[dim]Ctrl-C to quit · run with --help for scripting[/]",
                            border_style="magenta"))
    try:
        kb = open_keyboard(args)
    except DeviceError as e:
        console.print(f"[red]{e}[/]")
        return 1
    menu = {
        "1": "Status / battery", "2": "Lighting effect", "3": "Solid colour (custom mode)",
        "4": "Sleep timer", "5": "Key response time", "6": "Fn switch",
        "7": "Remap a key", "8": "Reset key assignments", "q": "Quit",
    }
    try:
        with kb:
            while True:
                table = Table(box=None, show_header=False)
                for k, v in menu.items():
                    table.add_row(f"[bold cyan]{k}[/]", v)
                console.print(table)
                choice = Prompt.ask("Select", choices=list(menu), default="1")
                if choice == "q":
                    return 0
                if choice == "1":
                    show_status(kb)
                elif choice == "2":
                    cmd_modes(args)
                    mode = IntPrompt.ask("Mode", default=1)
                    b = IntPrompt.ask("Brightness 1-5", default=keys.DEFAULT_BRIGHTNESS)
                    s = IntPrompt.ask("Speed 1-5", default=keys.DEFAULT_SPEED)
                    kb.set_light(mode, b, s)
                    ok("lighting updated")
                elif choice == "3":
                    rgb = parse_color(Prompt.ask("Colour (name or RRGGBB)", default="white"))
                    colors = {led: rgb for _, _, led, _, _ in keys.PHYSICAL_KEYS}
                    console.print(render_keyboard(colors))
                    kb.set_custom_colors(colors)
                    ok("colour stored")
                elif choice == "4":
                    m = Prompt.ask("Sleep after (minutes)", choices=list(SLEEP_OPTIONS))
                    kb.set_sleep(SLEEP_OPTIONS[m])
                    ok(f"sleep timer: {m}")
                elif choice == "5":
                    g = IntPrompt.ask("Gear (1 fastest)", choices=["1", "2", "3"])
                    kb.set_response(g)
                    ok(f"response gear {g}")
                elif choice == "6":
                    m = Prompt.ask("Mode", choices=["normal", "fn"])
                    kb.set_fn_switch(m == "fn")
                    ok(f"Fn switch: {m}")
                elif choice == "7":
                    src = keys.key_code(Prompt.ask("Physical key (e.g. capslock)"))
                    dst = keys.target_code(Prompt.ask("New function (e.g. esc, volup)"))
                    kb.remap(0, src, dst)
                    ok(f"{keys.code_name(src)} → {keys.code_name(dst)}")
                elif choice == "8":
                    if Confirm.ask("Reset all key assignments?", default=False):
                        kb.reset_keys()
                        ok("keys reset")
    except KeyboardInterrupt:
        console.print()
    return 0


# -- argument parsing -------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ak820ctl", description="AJAZZ AK820 Max Plus control")
    p.add_argument("--device", help="hidraw node (default: auto-detect)")
    p.add_argument("-n", "--dry-run", action="store_true", help="print packets, send nothing")
    p.add_argument("-v", "--verbose", action="store_true", help="show packets sent")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")

    sub.add_parser("tui", help="full-screen interface (default)").set_defaults(func=cmd_tui)
    sub.add_parser("menu", help="simple prompt menu").set_defaults(func=interactive)
    sub.add_parser("devices", help="list detected interfaces").set_defaults(func=cmd_devices)
    sub.add_parser("status", help="battery and link state").set_defaults(func=cmd_status)
    sub.add_parser("modes", help="list lighting modes").set_defaults(func=cmd_modes)

    s = sub.add_parser("light", help="set a lighting effect")
    s.add_argument("mode", type=int)
    s.add_argument("-b", "--brightness", type=int, default=keys.DEFAULT_BRIGHTNESS)
    s.add_argument("-s", "--speed", type=int, default=keys.DEFAULT_SPEED)
    s.add_argument("-d", "--direction", type=int, default=0)
    s.add_argument("-c", "--color", type=int, default=0, help="palette index")
    s.set_defaults(func=cmd_light)

    for name, func, helptext in (("custom", cmd_custom, "store per-key colours"),
                                 ("frame", cmd_frame, "send a live frame (experimental)")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("keys", nargs="*", metavar="KEY=COLOR", help="e.g. esc=red w=00ff00")
        s.add_argument("-a", "--all", type=parse_color, help="base colour for every key")
        if name == "custom":
            s.add_argument("-b", "--brightness", type=int, default=keys.DEFAULT_BRIGHTNESS)
        s.set_defaults(func=func)

    s = sub.add_parser("sleep", help="auto-sleep timer")
    s.add_argument("minutes", choices=list(SLEEP_OPTIONS))
    s.set_defaults(func=cmd_sleep)

    s = sub.add_parser("response", help="key response time gear")
    s.add_argument("gear", type=int, choices=[1, 2, 3])
    s.set_defaults(func=cmd_response)

    s = sub.add_parser("fn-switch", help="F-row default layer")
    s.add_argument("mode", choices=["normal", "fn"])
    s.set_defaults(func=cmd_fn_switch)

    s = sub.add_parser("remap", help="assign a key or media function to a key")
    s.add_argument("src", nargs="?")
    s.add_argument("dst", nargs="?")
    s.add_argument("--fn", action="store_true", help="Fn layer")
    s.add_argument("--list-targets", action="store_true")
    s.set_defaults(func=cmd_remap)

    s = sub.add_parser("macro", help="store a keyboard macro on a key (options before SRC)")
    s.add_argument("src")
    s.add_argument("events", nargs=argparse.REMAINDER,
                   help="'+a' press, '-a' release, 'a' tap, '@ms' delay")
    s.add_argument("--fn", action="store_true", help="Fn layer")
    s.add_argument("-r", "--repeat", type=int, default=1)
    s.add_argument("--delay", type=int, default=10, help="default delay ms")
    s.set_defaults(func=cmd_macro)

    sub.add_parser("reset-keys", help="restore default key assignments").set_defaults(
        func=cmd_reset_keys)
    s = sub.add_parser("factory-reset", help="restore factory settings")
    s.add_argument("-y", "--yes", action="store_true")
    s.set_defaults(func=cmd_factory_reset)

    s = sub.add_parser("raw", help="send cmd+args after the AA55CC33 header")
    s.add_argument("hex", nargs="+")
    s.add_argument("--reply", action="store_true")
    s.set_defaults(func=cmd_raw)
    return p


def cmd_tui(args):
    try:
        from .tui import run
    except ImportError:
        raise SystemExit("the TUI needs Textual: pip install textual")
    run(args.device, args.dry_run)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.command:
            try:
                import textual  # noqa: F401
            except ImportError:
                return interactive(args)
            cmd_tui(args)
            return 0
        args.func(args)
    except (DeviceError, KeyError, ValueError) as e:
        console.print(f"[bold red]error:[/] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
