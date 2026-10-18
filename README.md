# ak820ctl

linux driver for the ajazz ak820 max plus (the tri-mode rgb one). it does lighting, per-key colors, key remaps, macros, sleep/response settings and battery status, over the usb cable or the 2.4g dongle.

![per-key rgb tab](https://raw.githubusercontent.com/shrey715/ak820ctl/main/docs/tui-rgb.svg)

> [!WARNING]
> this is an unofficial project. i'm not affiliated with ajazz in any way. the protocol was worked out by reverse engineering their windows driver (v1.0.4.6), and as of the first release none of it has been checked against a real usb capture. it only sends the same settings packets the official app sends and doesn't touch firmware, but use it at your own risk. if something acts weird, `ak820ctl factory-reset` should put the keyboard back to stock.

## install

```sh
pipx install ak820ctl
```

then let your user talk to the keyboard without sudo:

```sh
sudo curl -o /etc/udev/rules.d/70-ajazz-ak820.rules \
  https://raw.githubusercontent.com/shrey715/ak820ctl/main/udev/70-ajazz-ak820.rules
sudo udevadm control --reload && sudo udevadm trigger
```

unplug and replug the dongle or cable after that.

## usage

run `ak820ctl` with no arguments to get the tui.

- lighting: pick an effect from the list, and the sliders it doesn't use grey out
- per-key rgb: click or drag across the keyboard map to paint, fill patterns (rainbows, gradients, a wasd highlight), save your designs as presets, then upload
- remap and macro: click the key you want on the map, remapped keys get tinted, and you can restore any of them one by one
- settings: sleep timer, key response, fn switch, factory reset

the keyboard can't report its settings back, so the tui keeps track of what it last sent in `~/.config/ak820ctl` and opens where you left off. `1`-`5` switch tabs, `ctrl+s` applies the current one, `l` shows the packet log and `?` has the rest.

![remap tab](https://raw.githubusercontent.com/shrey715/ak820ctl/main/docs/tui-remap.svg)

everything is also available as plain commands if you want to script it:

```sh
ak820ctl status                  # battery + link state
ak820ctl modes                   # list lighting effects
ak820ctl light 7 -b 5            # static light, full brightness
ak820ctl light 8 -s 3            # breathing at speed 3
ak820ctl custom -a 101010 esc=red w=cyan a=cyan s=cyan d=cyan
ak820ctl sleep 30                # 5 | 15 | 30 | never
ak820ctl response 1              # key response gear, 1 is fastest
ak820ctl fn-switch fn            # normal | fn
ak820ctl remap capslock esc
ak820ctl remap --fn f1 playpause
ak820ctl remap --list-targets
ak820ctl macro f12 +lctrl c -lctrl   # ctrl+c on f12
ak820ctl reset-keys
ak820ctl menu                    # old-school prompt menu
```

macro events: `+key` presses, `-key` releases, a bare `key` taps it, and `@ms` sets the delay after an event (like `a@200`). flags like `--fn` or `-r 3` go before the key name.

`-n` / `--dry-run` prints the packets and sends nothing, and `-v` shows every packet that goes out. both work with the tui too (`ak820ctl -n`).

## what works and what doesn't

decoded from the driver: lighting effects with brightness/speed/direction, per-key colors (custom mode), sleep timer, key response time, the fn switch, remapping to keys or media functions, keyboard macros, and the battery/link query.

still open (see the issues tab): what the effect color index numbers mean, live streaming frames, one unidentified command (`0x0A`), firmware updates and mouse-button assignments.

if you own one of these, running `ak820ctl -v status` and posting what comes back helps a lot.

## how it works

every command is a 64-byte hid output report that starts with `aa 55 cc 33`, sent to the vendor hid interface (usage page `0xff02`). [PROTOCOL.md](https://github.com/shrey715/ak820ctl/blob/main/PROTOCOL.md) has the full command table and the driver function each finding came from.

## dev

```sh
git clone https://github.com/shrey715/ak820ctl && cd ak820ctl
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

releases are automatic: bump `__version__` in `ak820/__init__.py` and push to main. the publish workflow runs the tests, uploads to pypi through trusted publishing (no tokens anywhere) and makes a github release. pushes that don't change the version just run the tests.

## license

mit. "ajazz" and "ak820" are their owner's trademarks and only used here to say what hardware this is for.
