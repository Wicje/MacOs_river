# Third-party compatibility record

The owner's rule: pixel fidelity to macOS is standing, and every
third-party piece the shell leans on is tracked so an upstream update
cannot silently break the session. This file lists each component, the
version the shell was built against, and **what to re-check** when pacman
or the project ships an update.

Checked 2026-10-24 (Arch, pacman -Q):

| component        | version   | what breaks if updated                                                        |
|------------------|-----------|--------------------------------------------------------------------------------|
| river + riverctl | 0.3.17-1  | the JSON controller socket (`macui/river.py`) is a private hook: vet `get-views`, `get-focused-view`, `get-tags`, move/focus verbs after any river upgrade; layer-shell pointer routing changed historically |
| gtk3             | 3.24.52-2 | cairo/gdk internals used via ctypes (`panel.update_input_region`, `gdk_window_input_shape_combine_region`) |
| gtk-layer-shell  | 0.10.1-1  | `set_keyboard_interactivity` is already deprecated → `set_keyboard_mode` exists in this version; migrate during the next idle pass |
| python           | 3.14.8-1  | stdlib-only policy protects this; PyGObject 3.58.1 GI deprecations (GLib.unix_fd_add_full → GLibUnix.fd_add_full) are warned, not fatal |
| WhiteSur icons   | local 2026-10-23 | icon *names* (`apps.py:icon_path` scopes) upstream renames icons → re-verify fire­fox/spotify/dolphin/gimp/audacity/obs/steam paths after theme update |
| ydotool          | 1.0.4-2   | the daemon: root-owned socket `/tmp/.ydotool_socket` (chmod 666 for tests); `-a` mapping on this panel skews toward the bottom-right, verify before scripted UI raster tests |
| wl-clipboard     | 2.3.0-1   | spotlight calc copies results via `wl-copy` |
| grim             | 1.5.0-2   | empty-workspace screenshots for review |

Session-known footguns, re-stated because they recur:

- `pkill -f <pattern>` kills this shell's own wrapper when the pattern
  appears in the wrapper argv, wedging the call for 120 s. Kill by
  recorded PID or by `/proc/*/exe` exact-match scans only.
- A same-connection synchronous DBus call from inside its own
  GMainLoop callback deadlocks; defer with `GLib.idle_add`.
- river 0.3 delivers pointer events to layer surfaces in the **overlay
  and top** layers, measured against `catchtest`; **bottom-layer surfaces
  receive none**, even on empty space. Any panel that must be clicked
  on a layer below its neighbors needs an industry input-region that
  excludes live views (geometry available from `river.views()`).

## round of 2026-10-24 evening (examined + touched)

| component       | version   | what it touches, what breaks on update |
|------------------|-----------|----------------------------------------|
| SF Pro Text      | local, 26 faces | **installed already** (`fc-match "SF Pro Text"` → SF-Pro-Text-Regular.otf); glyph/rendering truth, nothing to install |
| Inter            | inter-font 4.1-1 | fallback family baked into `macui/draw._font_desc` default family chain; keep |
| paplay (pipewire-tools) | installed | `--volume=` takes **0..65536** linear, not 0.0..1.0 (`macui/sound.play` already converts) |
| gtklock          | 4.0.0-1   | powerbar + playerctl module names (`playerctl-module.so`, `powerbar-module.so`) passed via `-m`; config keys are long-only (`--background`, `--time-format`); PAM file `/etc/pam.d/gtklock` ships with the package |
| faster-whisper   | ~/venvs/voice (3.12.13) | called through `~/bin/_voice.py stt` at model `base`; upgrade ⇒ re-check dictation latency (model loads per call, ~8 s) |
| wtype            | installed | stdin `-` types the transcript |
| pw-record        | installed | `--rate 16000 --channels 1` to a wav path; **SIGINT** flushes a valid file, SIGKILL does not — kill the recorder gently for the dictation stop |
