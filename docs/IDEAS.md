# macOS ideas for macshell — research and build order

Sources: the owner's suggestion list (workspace-aware dock, contextual
dock, notch island, Spotlight, system bar, stage manager, widgets,
Quick Look, lock screen, glass), plus what the reference shot
`~/mac/maclin.jpg` shows, plus the behavior macOS ships today
(Tahoe 26: Liquid Glass language, keyboard Spotlight, magnetized dock,
Dynamic Island). Nothing here is creative decoration: every entry says
what already exists in the shell and what the build costs.

Standing rule the owner set: the look must be **pixel-faithful to
macOS**, and every third-party component the shell leans on must be
tracked for updates (`docs/COMPAT.md`).

## 1. The notch as a Dynamic Island (top priority)

macOS: a black pill that idles into the notch and blooms into
information; on Linux nothing exists that does this, and it is the
single most-recognizable behavior we can port.

Build as an activity registry (the owner's priority table):

| priority | activity              | presentation            |
|----------|-----------------------|-------------------------|
| critical | recovery error        | immediate alert         |
| high     | failed command        | expanded notification    |
| normal   | active download       | persistent progress      |
| low      | music                 | compact state            |
| background | completed build     | temporary animation      |

- each activity: id, type, status, progress, action handler
- only the highest-priority activity shows
- idle → small pill; active → expanded panel; click → interactive panel
- spring animation with tick callbacks (`panel.slide_to` pattern the
  dock already uses); restrained — no bounce

Integrations, cheapest first:

1. **MPRIS music** — DBus `org.mpris.MediaPlayer2.*`: artwork, title,
   progress, play/pause/next. The shell already hosts DBus (tray).
2. **Long-command notifications** — `TMPDIR/macshell-*` marker files
   plus a `mac-activity` CLI: `mac-activity start "build"`, `done`.
   Priority mapping per the table above.
3. **Downloads** — the same registry, progress parsed from wrappers.
4. **Battery/hardware** — the notch already gets LED states; sensors
   exist (`sensors.py`), only the pill presentation is missing.

## 2. Spotlight beyond launch (medium)

Exists: app search, floor branching, and now the calculator
(`2*(3+4)` → result, AST-walked, nothing interpreted).

Add, in order:

1. **Fuzzy ranking** — `difflib` sequence ratio plus recency bump; no
   extra dependency (the box has 3.7 GB; keep stdlib only).
2. **Clipboard history (text first)** — a clipboard watcher records
   recent text in memory; the palette row "clipboard" lists entries
   and pastes through `wl-copy`. Images later.
3. **Command palette** — fixed verbs (open project, tile left/right,
   kill port 3000, reveal in Finder) executed by the shell, never raw
   text into a shell.
4. **Project-aware rows** — index a small list of project roots
   (`~/.config/macshell`, `~/mac`, Continua's tree, ANICHISOM); query
   "continua" → open project / open terminal here / run tests.

## 3. The dock as workspace-aware shelf (highest impact per line)

The shell already speaks river's controller socket
(`macui/river.py`: `views()`, `focused_view()`, `running_apps()`).
So instead of a static `APPS` list:

- **per-tag rows**: a pinned set per river tag (1 coding, 2 research,
  3 design, 4 communication) chosen from what each tag was last used
  for
- **running dots**: an app running on another tag gets a dot — macOS
  shows the same for background instances
- **click = find, else launch**: if the app already has a window on
  any tag, the dock moves river's focus there instead of spawning a
  second one (`river.call("...")` — the controller supports the
  move/focus verbs `riverctl` maps are backed by)

## 4. Widgets that are real (medium)

Existing: analog clock, weather + forecast, calendar, gauges, screen
time. Add, each actionable:

- **dev widget**: git branch of the active project, uncommitted
  count, last build status (from the same activity registry)
- **focus timer**: session length active task remaining time
- click-to-open target: the terminal/project, never a generic viewer

## 5. Menu-bar profiles (light)

Same refresh loop, three profiles chosen by focused app category:
coding (git branch, CPU, mem), creative (media controls), presentation
(clock only, no notifications). Manual override in the control
centre.

## 6. Pixel-faithful appearance pass (required by the owner)

- **fonts**: SF Pro is licensed; closest open metric is
  **Inter** (`inter-font` in Arch repos) at the same optical sizes
  macOS uses; letter-spacing stays default, weights 400/500/600
- **icons**: WhiteSur theme already installed — this IS the pixel
  source of truth for app icons; keep to its row sizes
- **dock**: magnification curve macOS uses (quadratic on distance),
  bounce animation on launch, running dots under icons
- **menubar**: text 13px-type; the spacing between menus matches
  macOS Terminal spacing ("File Edit View Window Help")
- **translucency**: river 0.3 does not blur → dark translucent
  fills with a 1px light top hairline and a small shadow reproduces
  the Liquid Glass read without a blur engine
- **notch**: geometry drawn around the physical corner of the panel

## 7. Flotsam the comparison shot lists (already built or cheap)

- window apps sorry Quick Look — already built; refine per format
- stage manager — built; group tiles get river-backed focus
- lock screen visual (clock/date/battery) on top of river's lock
- desktop right-click menu — built, waiting on the pointer pass
- system sounds (shutter, screen-open thock) — small, add last

## Eighth — what we deliberately do NOT build

- a real macOS Menus provider per app (Linux apps own their menus;
  the styled fake menus stay)
- swap-transparency sampling behind panels (needs compositor
  capture river does not expose)

## Build order

1. notch activity registry + MPRIS (people notice this first)
2. dock per-tag rows + find-vs-launch + running dots
3. spotlight fuzzy + clipboard + commands
4. appearance pass with the reference pinned next to it
5. widgets dev/focus
6. sounds, lock screen polish
