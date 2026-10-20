# macshell — a macOS Tahoe desktop for Wayland

A macOS-like shell for River/Sway: a translucent menu bar with a notch, a
magnifying dock, a Control Centre, a widget column, Spotlight, Launchpad,
Mission Control, an app switcher, a Stage Manager, a notification centre
and a rotating wallpaper.

Everything is drawn with Cairo on GTK layer-shell surfaces, so it works on
any wlroots compositor.

![panels](https://img.shields.io/badge/wayland-river%20%7C%20sway-6c5ce7)

## What is in the box

| Panel | Shortcut | What it does |
|-------|----------|--------------|
| Launchpad | `Super+D` | grid of the installed applications, with a search field |
| Spotlight | `Super+Space` | searches applications, folders, does arithmetic and web searches |
| Control Centre | `Super+C` | Wi-Fi, Bluetooth, Focus, brightness, sound, now playing, power mode, utilities |
| Apple menu | `Super+Shift+A` | about, system settings, sleep, restart, log out |
| App switcher | `Super+Tab` | the running applications in a row, the focused one highlighted |
| Mission Control | `Control+Up` | every open window as a card, click to raise it |
| Stage Manager | `Super+G` | the strip of open windows along the left edge |
| Notification Centre | click the clock | calendar, clock and the notifications mako collected |
| Assistant | `Super+Shift+K` | asks a local model: a question, the screen, or a text to rewrite |
| Writing Tools | `Super+V` → *Writing Tools…* | rewrite, proofread, summarise, change the tone |
| Screenshot toolbar | `Alt+S` | the floating macOS toolbar: area, window, screen and timers |
| Hide the Dock | `Super+Shift+T` | only hides; `Super+Shift+T` again is not needed |
| Hide the Notch | `Super+Shift+Q` | only hides |
| Hide the widgets | `Super+Shift+G` | only hides |
| Spaces | top right corner | the dots switch between the nine tags |

## The dock and the notch

Both behave the way macOS does it, and both have three modes in
**System Settings → Desktop & Dock**:

* **Always** — the panel never hides.
* **Desktop** — the panel is on the screen while the desktop shows and
  steps aside as soon as an application takes the focus.
* **Auto** — the panel is only there when the pointer reaches the edge of
  the screen.

The dock slides down and up instead of blinking, and the notch slides
under the top edge.  A thin strip along the bottom of the screen is the
hot zone of the dock; the menu bar itself is the hot zone of the notch.

Because River keeps the activation of the last focused window even when
that window sits on another workspace, the shell asks the compositor for
the workspace that is on screen before it decides that an application is
in front.  The workspace switch (`Super+1` … `Super+9`) therefore goes
through the shell.

## The assistant

The assistant talks to a **local ollama server**, so nothing leaves the
machine.  It does three things:

* **Ask** — a free question, the way Spotlight asks Siri.
* **Write** — the Writing Tools: rewrite, proofread, summarise, make it
  formal, friendly or shorter.
* **Screen** — Visual Intelligence: what is on the display right now.

Install a model once:

```sh
ollama pull llama3.2      # for Ask and Write
ollama pull llava         # for Screen
```

Without a model the panel says so instead of failing.

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
  `makoctl`, `wl-clipboard`, `wtype`, `grim`, `ollama`

## The appearance

**System Settings → Appearance** carries the Liquid Glass controls of
macOS: the accent colour, the opacity of the panels and how much accent
colour they carry, plus *reduce transparency*.  The dark theme draws the
panels in dark glass, so the text stays readable whatever the wallpaper
does.

## How the shell finds out what is running

River Classic has no introspection command in `riverctl`, so the shell talks
the `wlr-foreign-toplevel-management` protocol directly with a small C
helper (`tools/toplevels/`).  It reports every window with its title, its
application id and which one is focused, which is what the menu bar, the
dock's running indicators and the Force Quit list are built from.

## The clicks that reach the windows

A layer-shell surface takes the pointer over its whole rectangle, even
where it is transparent.  The dock therefore tells the compositor which
part of its surface is real, so the windows underneath can be clicked
through the space between the icons and the shelf.
