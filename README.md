# macshell — a macOS Tahoe desktop for Wayland

A macOS-like shell for River/Sway: a translucent menu bar with a notch, a
magnifying dock, a Control Centre, a widget column, Spotlight, Launchpad,
Mission Control, a notification centre and a rotating wallpaper.

Everything is drawn with Cairo on GTK layer-shell surfaces, so it works on
any wlroots compositor.

![panels](https://img.shields.io/badge/wayland-river%20%7C%20sway-6c5ce7)

## What is in the box

| Panel | Shortcut | What it does |
|-------|----------|--------------|
| Launchpad | `Super+D` | grid of the installed applications, with a search field |
| Spotlight | `Super+Space` | searches applications, folders, does arithmetic and web searches |
| Control Centre | `Super+C` | Wi-Fi, Bluetooth, Focus, brightness, sound, appearance |
| Apple menu | `Super+Shift+A` | about, system settings, sleep, restart, log out |
| Mission Control | `Super+Tab` | every open window as a card, click to raise it |
| Notification Centre | click the clock | calendar, clock and the notifications mako collected |
| Hide the Dock | `Super+Shift+T` | only hides; `Super+Shift+T` again is not needed |
| Hide the Notch | `Super+Shift+Q` | only hides |
| Hide the widgets | `Super+Shift+G` | only hides |
| Spaces | top right corner | the dots switch between the nine tags |

## Install

```sh
git clone <this repository> ~/.config/macshell
cd ~/.config/macshell
./install.sh
```

`install.sh` copies the river scripts into `~/.config/river`, installs the
systemd user units, builds the small helper that lists the compositor's
windows and enables both services.

## Requirements

* `river` (or `sway`) with layer-shell support
* `gtk3`, `python3-gobject`, `pycairo`, `python3-gi`
* `wayland-scanner` and a C compiler for the toplevel helper
* optional: `playerctl`, `wpctl`, `brightnessctl`, `nmcli`, `bluetoothctl`,
  `makoctl`, `wl-clipboard`, `wtype`

## How the shell finds out what is running

River Classic has no introspection command in `riverctl`, so the shell talks
the `wlr-foreign-toplevel-management` protocol directly with a small C
helper (`tools/toplevels/`).  It reports every window with its title, its
application id and which one is focused, which is what the menu bar, the
dock's running indicators and the Force Quit list are built from.
