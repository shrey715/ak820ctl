# ak820ctl

Control the **AJAZZ AK820 Max Plus** without the Windows app: lighting effects, per-key RGB, key remaps, macros, music sync, sleep and battery. Works over the USB cable or the 2.4G dongle.

![the tui lighting tab with a live effect preview](https://raw.githubusercontent.com/shrey715/ak820ctl/main/docs/tui-lighting.svg)

> [!WARNING]
> Unofficial. Not affiliated with AJAZZ. The protocol was reverse engineered from the vendor's Windows driver, and the lighting, colours, per-key RGB and live frames have been confirmed on real keyboards. It only sends the settings packets the official app sends and never touches firmware. Use at your own risk; `ak820ctl factory-reset` puts the keyboard back to stock.

## Get it

Pick one:

| | |
|---|---|
| **Web, no install** | open **[ak820ctl.vercel.app](https://ak820ctl.vercel.app)** in Chrome, Edge or Opera on a computer |
| **pipx / uv** | `pipx install 'ak820ctl[music]'` or `uv tool install 'ak820ctl[music]'` |
| **AppImage** | grab it from [releases](https://github.com/shrey715/ak820ctl/releases/latest), `chmod +x`, run |

### Linux permissions

Once, so you don't need sudo (the web app needs this too):

```sh
ak820ctl udev --install      # then replug the keyboard or dongle
```

It only opens the keyboard's settings interface to your user, never the typing one.

## Use it

```sh
ak820ctl                          # full-screen TUI
ak820ctl status                   # battery
ak820ctl light breathing -c cyan  # effect + colour (ak820ctl modes lists them)
ak820ctl lights off               # and `on` brings your lighting back
ak820ctl custom -a 101010 w=red a=red s=red d=red
ak820ctl remap capslock esc
ak820ctl macro f12 +lctrl c -lctrl
ak820ctl music --style pulse      # lights follow what's playing
ak820ctl --help                   # everything else
```

## What doesn't work (yet)

- Bluetooth: the keyboard doesn't expose its settings over Bluetooth, so plug in the cable or dongle to change things.
- Phones: browsers on phones don't support WebHID.
- Firmware updates and mouse-button assignments aren't supported.

More detail: [PROTOCOL.md](https://github.com/shrey715/ak820ctl/blob/main/PROTOCOL.md) · [issues](https://github.com/shrey715/ak820ctl/issues)

## Credits

Hardware test results, the colour palette, live-frame behaviour and the effect previews come from [prasoondev/ajazz-linux](https://github.com/prasoondev/ajazz-linux) (MIT).

MIT licensed. "AJAZZ" and "AK820" are trademarks of their owner, used here only to say what hardware this is for.
