# What is left to do

The list of the open ends of the shell, in the order they should be
picked up.  Every item says what was found out and what is missing.

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
  when the dock is on the screen (`(38, 30, 742, 72)`), but it is only
  written when the surface is mapped or resized, and not when the dock
  slides.  If the region is stale, the clicks fall on the window below.
  → Call `update_input_region()` whenever the offset of the dock
  changes, and check whether river honours the input region of a
  layer-shell surface at all.
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

## 3. The speech of the machine

The voice tooling of the machine is there (`~/bin/vrec`, `vsay`, `vchat`),
but it is a program in a terminal.  The shell has no button for it yet.

What to build:

* a small panel with a microphone, the way macOS has the dictation of
  the keyboard settings: click, speak, and the text goes into the
  window that has the focus;
* the recording with `pw-record` (or `parec`), the transcription with
  the faster-whisper of `~/venvs/voice`, and the text into the focused
  window with `wtype` (or through the clipboard with `wl-copy` and
  `wtype -k ctrl v`);
* the place for the button: the notch has a row of round buttons
  already, and the Control Centre has a tile for every switch.

The whisper of the machine is slow (about eight seconds for a sentence,
the model is loaded every time), so the panel should show that it is
working and let the model stay loaded.

## 4. Smaller things

* The tiles of the Control Centre and the buttons of the notch are
  written down in `config.json`; the file is in the repository, so the
  choices of the user come along with every commit.
* The `MissionControl` and the `Settings` panel put a `GtkEntry` into a
  window that already has a `GtkDrawingArea`; GTK complains about it
  when the shell starts.
* `GLib.unix_fd_add_full` is deprecated; the new `GLibUnix.fd_add_full`
  wants to be used.
* The `snap zone` of the edges of the screen is gone (the edges belong
  to the applications now), but the README still offers it.  The
  keyboard tiling draws the same rectangle, and that part works.
* The tiling with the quarters (`Control+Alt+1…4`) and with the top and
  the bottom half (`Control+Alt+↑/↓`) does not do anything: the command
  `tile:` hands only "left" and "right" to `Shell.snap_window`, and the
  other zones are dropped on the way.
* The `open_launchpad` of the Control Centre and of the dock toggles the
  Launchpad: a second click closes it again.
* The dock's own `show_dock` sets a time (`_dock_until`) that nothing
  read until now; it is read now, but the dock hides itself again after
  two seconds and a half when an application is in front.
* The screen time of the applications is counted per day, but the
  counter is not reset when the day changes.
