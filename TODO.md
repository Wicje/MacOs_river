# What is left to do

The list of the open ends of the shell, in the order they should be
picked up.  Every item says what was found out and what is missing.

## 5. The phone hub — verified by the owner 2026-10-25

**State:** the laptop side was wired and unit-verified; the owner then
opened it from a real phone and the tests passed, clipboard and files
included.  Nothing is waiting here any more.

* `tools/phonehub.py` serves the clipboard both ways, notifications for
  links and `~/Downloads/phone` for files; every route carries the
  pairing token from `~/.local/state/macshell/phonehub.json`.
* Started and stopped from the Control Centre tile / the notch action /
  the fifo (`echo phonehub > $XDG_RUNTIME_DIR/macshell.cmd`); the pid is
  in `/tmp/phonehub.pid`, the log in `/tmp/phonehub.log`.
* The page is kept friendly to insecure contexts on purpose: the hub is
  plain `http://` on the LAN, where `navigator.clipboard` does not
  exist, so the copy falls back to `execCommand` inside the click
  gesture (Safari drops writes that happen after an await).
* What a real phone still has to prove: Safari keeps the fetch alive
  (HTTP/1.1 was turned on for that), the file upload from the pickers,
  and a duplicate file landing as `name (1).ext`.

## 1. The Launchpad icon of the dock does not open the Launchpad

**State:** not solved.  The code is right, the click never arrives.

What is known:

* The path of the command works: `echo launchpad > $XDG_RUNTIME_DIR/macshell.cmd`
  opens the grid, and so does `echo dockclick:0` (a command that calls
  `Dock.activate_index(0)`, the very function a click calls).
* The layout is right: the icon of the Launchpad is the first item of
  the row, at x 48…94 of the surface, and the surface is 818…870 wide
  and centred, so the icon is around x 300…340 of the screen.
* The pointer reaches the dock: the icons grow under the pointer, so
  the motion events are delivered.
* The button events are the ones that are missing.

What to look at:

* The input region of the dock (`Dock.input_rects`) is handed to GDK
  with `gdk_window_input_shape_combine_region`.  The region is right
  when the dock   is on the screen (`(38, 30, 742, 72)`), but it is only
  written when the surface is mapped or resized, and not when the dock
  slides.  If the region is stale, the clicks fall on the window below.
  → FIXED (2026-10-25): `update_input_region()` is now called on every
  magnification step in `Dock._step`.  Magnification is exactly when the
  region goes stale: the row grows outward from the centre, `shelf_x`
  moves left, and the left end of the row — Launchpad is the first icon
  — falls outside the old region.  Whether river honours the input
  region of a layer-shell surface at all still has to be confirmed by a
  real click.
* The strips (`Sensor`) are mapped after the panels, so they get the
  pointer first.  The bottom strip is four pixels high, but it is worth
  checking that it does not overlap the row of icons.
* `Panel._on_button` only reacts to `BUTTON_PRESS`.  The press may
  arrive as a release, or the event may be delivered to the window
  instead of the drawing area.

How to try it without a mouse: `ydotool` moves the pointer on this
machine, but its clicks do not arrive as button events, so the click has
to be tried with a real mouse.

## 2. Ghostty cannot run on this machine

Ghostty wants OpenGL 4.3, and the Intel HD 2000 of this laptop gives
OpenGL 3.3:

```
info(opengl): loaded OpenGL 3.3
warning(opengl): OpenGL version is too old. Ghostty requires OpenGL 4.3
```

The dock says so now (the line that names the problem is the one that
is shown), and the dock carries **Kitty** instead.  Kitty runs on this
machine.

## 3. The speech of the machine — SOLVED 2026-10-24/25

The Control Centre has a **dictation** tile (mic glyph): first click
starts `pw-record` (16 kHz mono → /tmp/dictation.wav, pid in
/tmp/dictation.pid), the second click SIGINTs it (verified: SIGINT
flushes a valid WAV, SIGKILL does not), notifies "Transcribing…", runs
faster-whisper (`~/venvs/voice`, model `base`, ~8 s) and `wtype -`s the
transcript into the focused window. The middle of the pipeline was
verified with a synthetic recording on 2026-10-25: an `espeak-ng` wav
came back as the right text through `~/bin/_voice.py stt`. What is left
to try once, with the owner present, is the very first step (a real
voice through `pw-record`) and the very last (`wtype` into a real
window). The model loads per call; if the latency matters, keep the
venv warm (function to revisit).

The dictation tile was then used by the owner from the Control Centre
itself, with the real microphone, on the evening of 2026-10-25: the
recording and the typed sentence came out right, so the whole path is
proven and nothing is waiting here either.

## 6. The notification daemon (mako) — crash loop fixed 2026-10-25

While testing the phone hub the notifications died: mako restarted over
and over and systemd put it into the start limit.  What was wrong:

* The config carried a `[mode]` section that declared mode names.  Mako
  does *not* declare modes in its config — modes only exist at runtime
  (`makoctl mode -s …` sets the list) and the config only matches on
  them with criteria sections like `[mode=do-not-disturb]`.  A bare
  `[mode]` header cannot parse, so mako refused the whole file.  The
  section now matches the manual, and a notification under
  `do-not-disturb` stays in the history of the notification centre
  while it is invisible on the desktop — verified live.
* `state.set_dnd_mode` used `makoctl mode -t` — a *toggle*.  Switching
  from one focus mode to another left both turned on, and switching to
  "off" added a mode literally called "off" that never left.  It uses
  `makoctl mode -s` now (replaces the whole set; `-s` alone clears —
  both verified).
* `state.run` timed out after three seconds but killed only the shell
  around the command, and on this machine `/bin/sh` is bash, which
  leaves the inner command running: every `powerprofilesctl get` while
  the daemon was still starting leaked an orphan that kept holding the
  pipe.  `run` starts its own session now and kills the whole process
  group when the read does not come back (a hanging sleep leaves
  nothing behind — verified).

## 4. Smaller things

* The tiles of the Control Centre and the buttons of the notch are
  written down in `config.json`; the file is in the repository, so the
  choices of the user come along with every commit.
* The phone hub is its own feature now — see the section above.
* The `MissionControl` and the `Settings` warning is gone (2026-10-25):
  the entries now live in a `Gtk.Overlay` over the drawing area, the
  way the Launchpad always did it.
* `GLibUnix.fd_add_full` is used now (2026-10-25); the deprecated
  `GLib.unix_fd_add_full` is gone.
* The README no longer offers the pointer snap zone (the edges belong
  to the applications now); the keyboard tiling draws the same
  rectangle, and that part works.
* The tiling with the quarters (`Super+Control+1…4`) and with the top
  and the bottom half (`Super+Control+↑/↓`) works since 2026-10-24:
  the zones are mapped in `~/.config/river/init` **and** live-mapped;
  `tile_window` already understood the edge strings.
* The screen time resets when the day changes (`state._track_screen_time`
  and `screen_time()` both compare the `day` key) — that entry was
  outdated.
* The sound of the machine is its own feature now: `macui/sound.py`
  synthesizes the wavs (startup, trash, shutter, pop, tick, unlock,
  battery) and plays them with `paplay`.
* The `open_launchpad` of the Control Centre and of the dock toggles the
  Launchpad: a second click closes it again.
* The dock shows itself again for two and a half seconds when an
  application is in front (`_dock_until`), and hides itself again.
