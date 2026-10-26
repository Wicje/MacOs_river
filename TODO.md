# What is left to do

The list of the open ends of the shell.  Everything that could be
finished by the machine is finished — the only ends that stay open are
the ones that need the owner in the room (a real phone, a real mouse,
a real voice).

## What is actually left

* The notch shelf is the AirDrop stand-in: right-click a card and it
  goes to the nearest LocalSend receiver (the protocol is spoken
  directly in `macui/localsend.py` — discovery on UDP
  224.0.0.167:53317, then `prepare-upload2` + `upload`; HTTPS first,
  HTTP fallback, the receiver's PIN accepted from the 401 answer).
  AirDrop itself is impossible on this hardware — the Broadcom 4313
  cannot do AWDL.  Still open: with real phones in the room the
  consent tap happens on the receiver; and if two receivers answer at
  once we only take the first (phones first, then others) — a device
  chooser would be nicer, plus a send in hand to confirm the whole
  round with the owner's LocalSend running.
* The phone hub, with the owner's phone in hand: Safari keeping the
  fetch alive, one file upload through the pickers, and a duplicate
  file landing as `name (1).ext`.  (Section 5 below carries the whole
  story; nothing to code.)
* The wifi pane now answers at once even when the link is saturated —
  the strength read is cached for ten seconds, gets its timeout cut to
  1.5 s, and falls back to `/proc/net/wireless` if nmcli does not come
  back; the real fix though was the parse itself: this nmcli prints
  bare numbers (`100`), not `SIGNAL:100`, so strength had *always*
  read 0% in the pane — found and fixed 2026-10-26, the pane shows
  100% live.
* Ghostty stays out of the dock (section 2): permanent by hardware, no
  action possible.

Everything below is the record of what was found and fixed.

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

## 1. The Launchpad icon of the dock does not open the Launchpad — FIXED 2026-10-25, proven with real clicks 2026-10-25/26

**State:** solved.  The stale input region was the whole story.

* Root cause: the input region of the dock (`Dock.input_rects`) was
  only written when the surface was mapped or resized, never when the
  dock slid out or magnified.  The row grows outward from the centre,
  `shelf_x` moves left, and the left end of the row — Launchpad is the
  first icon — fell outside the old region, so those clicks dropped
  through to the window underneath.
* The fix (commit `0641832`): `update_input_region()` is called on
  every magnification step in `Dock._step`, so the region follows the
  row while it animates.
* Proof: real button events now arrive — a press/release pair was
  recorded on the dock surface (`panel mac-dock button … x=278.8
  y=66.7`, rects `(22.8, 30, 408, 72)`) and the click landed on the
  Terminal icon, focusing the foot window; the Launchpad itself opens
  from the fifo (`echo launchpad > …/macshell.cmd`) and via the dock
  row as before.  The owner's own mouse confirmed it in real use.
* Tooling that made this testable (documented for the next machine):
  root `ydotoold` (uinput is root-only here), socket
  `/tmp/.ydotool_socket` chmod 777 after each daemon restart,
  `ydotool mousemove -x N -y M` is relative and clamps at the screen
  edges, absolute mode (`-a`) is skewed by pointer acceleration, and
  the `debug` fifo verb dumps the dock layout, input rects and the
  last click straight into the journal.

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

* The badge/meter work is its own feature now: `mstatus` badge items
  (`NSStatusItem`-style), the wifi meter (`macui/traffic.py`,
  `bin/mstatus-net`, `bin/traffic`, hover reveal, popup rows and the
  Settings data-usage block) — all live-verified 2026-10-26.
* The wifi `0%` strength read — FIXED 2026-10-26: see the top of this
  file; the pane calls `state.wifi_strength()` (nmcli) synchronously in
  the paint, and with the network saturated the 3 s timeout used to
  trip and return ""; but the parse itself was the deeper bug and is
  corrected with a 10 s cache and a kernel fallback.
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
