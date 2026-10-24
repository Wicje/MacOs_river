"""The Tahoe dock.

A floating glass shelf of app icons that magnifies under the pointer the way
macOS does: neighbouring icons ease apart and grow, running apps carry a
small indicator dot and the hovered app shows a label bubble.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

DEFAULT_APPS = [
    {"id": "launchpad", "label": "Launchpad", "cmd": "", "special": "launchpad",
     "glyph": "grid", "app": ""},
    {"id": "firefox", "label": "Firefox", "cmd": "firefox", "app": "firefox"},
    {"id": "continua", "label": "Continua",
     "cmd": os.path.expanduser("~/.local/bin/continua-browser"),
     "app": "continua"},
    {"id": "dolphin", "label": "Files", "cmd": "dolphin", "app": "dolphin"},
    {"id": "terminal", "label": "Terminal", "cmd": "foot", "app": "foot"},
    {"id": "kitty", "label": "Kitty", "cmd": "kitty", "app": "kitty"},
    {"id": "vscode", "label": "Visual Studio Code", "cmd": "code", "app": "code"},
    {"id": "gimp", "label": "GIMP", "cmd": "gimp", "app": "gimp"},
    {"id": "mpv", "label": "mpv", "cmd": "mpv", "app": "mpv"},
    {"id": "audacity", "label": "Audacity", "cmd": "audacity", "app": "audacity"},
    {"id": "obs", "label": "OBS Studio", "cmd": "obs", "app": "obs"},
    # the native player runs in a terminal; the official client is
    # "spotify" and comes from the AUR
    {"id": "spotify", "label": "Spotify", "cmd": "foot -e spotify_player",
     "app": "spotify_player"},
    {"id": "steam", "label": "Steam", "cmd": "steam", "app": "steam"},
]

DOCK_CONFIG = os.path.expanduser("~/.config/macshell/dock.json")


def _load_apps():
    """The dock's items, with the user's changes applied."""
    try:
        with open(DOCK_CONFIG) as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return list(DEFAULT_APPS)
    if isinstance(saved, dict):
        # the new way: the row of the dock and the row of every tag
        saved = saved.get("apps")
    if not isinstance(saved, list):
        return list(DEFAULT_APPS)
    apps = []
    for entry in saved:
        if isinstance(entry, str):
            # the old way: only the ids of the built in list
            for known in DEFAULT_APPS:
                if known["id"] == entry:
                    apps.append(dict(known))
                    break
        elif isinstance(entry, dict) and entry.get("id"):
            # a program of its own, added from the launchpad
            apps.append({
                "id": entry["id"],
                "label": entry.get("label") or entry["id"],
                "cmd": entry.get("cmd", ""),
                "app": entry.get("app") or entry["id"],
                "special": entry.get("special", ""),
                "glyph": entry.get("glyph", ""),
            })
    return apps


def _save_apps(apps):
    """The dock keeps the whole entry, so a new program can be added."""
    try:
        try:
            with open(DOCK_CONFIG) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["apps"] = apps
        os.makedirs(os.path.dirname(DOCK_CONFIG), exist_ok=True)
        with open(DOCK_CONFIG, "w") as fh:
            json.dump(data, fh, indent=4)
    except OSError:
        pass


def _tag_rows():
    """The programs every workspace shows in its own dock row.

    River's tags are the workspaces; the config can name the dock row a
    tag belongs with (the working desk shows its tools, the research
    desk the reader).  A tag without a row keeps the whole dock.
    """
    try:
        with open(DOCK_CONFIG) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    rows = (data or {}).get("tags")
    if not isinstance(rows, dict):
        return {}
    return {str(tag): ids for tag, ids in rows.items()
            if isinstance(ids, list)}


APPS = _load_apps()

APP_IDS = {entry["id"] for entry in DEFAULT_APPS}
TRASH = {"id": "trash", "label": "Trash", "cmd": "dolphin trash:///"}

TOOLTIP_SPACE = 30

# how far the pointer has to be from an icon for it to stop growing
GROW_SPAN = 2.2


def _row_width(count, base, gap, pad_x):
    """The width of a row of icons at rest."""
    if count <= 0:
        return 0.0
    return count * base + (count - 1) * gap + pad_x * 2


def _growth(base, top, gap):
    """How much wider the row gets when the icons grow.

    The icons around the pointer swell and push their neighbours aside, so
    the row is wider than it is at rest.  The surface has to be wide
    enough for the widest row, or the glass is cut off and the icons at
    the end of the row hang outside the shelf.
    """
    span = base * GROW_SPAN
    step = base + gap
    extra = 0.0
    for distance in (0.0, step):
        if distance < span:
            t = 1.0 - distance / span
            extra += (top - base) * t * t * (3 - 2 * t)
    return extra * 2


def _measure(metrics, count):
    """The size of the icons and the width of the dock.

    The dock grows with the number of items, and the icons shrink when the
    row would not fit on the screen.
    """
    m = metrics
    count = max(1, count)
    base = m.px("dock_icon")
    gap = m.px("dock_gap")
    pad_x = m.px("dock_pad_x")
    top = m.px("dock_icon_max")
    width = _row_width(count, base, gap, pad_x) + _growth(base, top, gap)
    limit = max(240, (m.width or 1366) - 24)
    if width > limit and width > 0:
        factor = limit / width
        base *= factor
        gap *= factor
        pad_x *= factor
        top = base + (top - m.px("dock_icon")) * factor
        width = _row_width(count, base, gap, pad_x) + _growth(base, top, gap)
    return {"base": base, "gap": gap, "pad_x": pad_x, "top": top,
            "width": width}


class Dock(Panel):
    NAMESPACE = "mac-dock"

    def __init__(self, metrics, shell):
        m = metrics
        self._base_margin = int(m.px("dock_margin_bottom"))
        self._pad_y = m.px("dock_pad_y")
        self._icons: dict = {}
        self._last_click = None
        self._items_cache = self._build_items()
        self._size = _measure(metrics, len(self._items_cache))
        # the shelf slides inside the surface, so the surface itself stays
        # on the screen and the compositor keeps sending it frames
        self._slide_distance = 4 + self.shelf_height(metrics)
        super().__init__(
            metrics,
            layer="top",
            anchors={"bottom": True},
            # the surface stops short of the bottom edge: the strip that
            # watches the edge is never covered by the dock itself
            margins={"bottom": 4},
            exclusive=0,
        )
        self.shell = shell
        self.hover = -1
        self._layout: list = []
        self._shelf = (0, 0, 0, 0)
        self._offset = self._slide_distance
        self._sizes = [self._size["base"]] * len(self._items_cache)
        self._targets = list(self._sizes)
        self._animating = False
        self._bounce = -1
        self._bounce_started = 0.0

        width = self.panel_width()
        self.set_content_size(width, self.panel_height())
        screen = metrics.width or width
        self.set_horizontal_offset(int((screen - width) / 2))
        self._running = self._detect_running()
        self._windows = self._window_map()
        self._tag = 1

    # -- running apps --------------------------------------------------------

    def _build_items(self):
        """The dock's items: the programs, the recent ones and the trash.

        macOS keeps the last programs in front in a section of its own,
        so the dock does the same.
        """
        items = list(APPS)
        # the workspace's own row: a tag can pin the tools of the desk
        row = self._tag_rows().get(str(getattr(self, "_tag", 1)))
        if row:
            wanted = {str(entry) for entry in row}
            items = [entry for entry in APPS if str(entry["id"]) in wanted]
        known = {item["id"] for item in items}
        for app_id in state.recent_apps():
            label = state.friendly_name(app_id)
            if self._is_known(items, app_id, label):
                # the program is in the dock already: macOS does not show
                # it twice, not even under another name
                continue
            known.add(app_id)
            items.append({
                "id": app_id,
                "label": label,
                "cmd": "",
                "app": app_id,
                "recent": True,
            })
        items.append(TRASH)
        return items

    def _is_known(self, items, app_id, label):
        """True when a dock item is the same program as a recent one.

        The compositor calls a program by the name of its desktop entry
        and the dock by the name of the program itself, so Files is
        "dolphin" in the dock and "org.kde.dolphin" in the compositor.
        """
        plain = apps.plain_key(app_id)
        command = apps.command_for_id(app_id)
        for item in items:
            for key in (item.get("id"), item.get("app")):
                if not key:
                    continue
                if apps.plain_key(key) == plain:
                    return True
                if command and os.path.basename(key) == command:
                    return True
            name = (item.get("label") or "").lower()
            if label and name and name == label.lower():
                return True
        return False

    def _items(self):
        """The items of the dock, as they are right now.

        The list is kept as it is: the sizes of the icons are worked out
        for it, and a list that changes halfway would leave the icons and
        the shelf disagreeing about each other.
        """
        return self._items_cache

    def _window_map(self):
        """The open windows, by the id of their application."""
        windows = {}
        for entry in state.toplevels():
            app_id = (entry.get("app_id") or "").lower()
            if app_id and app_id not in windows:
                windows[app_id] = entry
        return windows

    def _detect_running(self):
        """App ids of the windows that are currently open."""
        try:
            return state.running_app_ids()
        except Exception:
            return set()

    def refresh_running(self):
        self._running = self._detect_running()
        self._windows = self._window_map()
        items = self._build_items()
        if items != self._items_cache:
            # a program came back into the recent section: the row is a
            # different length now, so the icons and the shelf are measured
            # again
            self._items_cache = items
            self._size = _measure(self.metrics, len(items))
            self._sizes = [self._size["base"]] * len(items)
            self._targets = list(self._sizes)
            self._resize()
        self.redraw()

    def _tag_rows(self):
        return _tag_rows()

    def refresh_span(self, tag):
        """The workspace changed, so the dock shows its row."""
        self._tag = int(tag)
        self.reload_apps()

    def reload_apps(self):
        """Pick up a changed list of dock items."""
        global APPS
        APPS = _load_apps()
        self._items_cache = self._build_items()
        self._size = _measure(self.metrics, len(self._items_cache))
        self._sizes = [self._size["base"]] * len(self._items_cache)
        self._targets = list(self._sizes)
        self._resize()

    def _resize(self):
        """Give the surface the size the row needs and centre it."""
        width = self.panel_width()
        self.set_content_size(width, self.panel_height())
        screen = self.metrics.width or width
        self.set_horizontal_offset(int((screen - width) / 2))
        self.redraw()

    # -- geometry ------------------------------------------------------------

    def panel_height(self, m=None):
        shelf_h = self._size["base"] + self._pad_y * 2
        return int(shelf_h + (self._size["top"] - self._size["base"])
                   + TOOLTIP_SPACE)

    def shelf_height(self, m=None):
        return self._size["base"] + self._pad_y * 2

    def panel_width(self):
        """Width of the dock surface.

        The surface is only as wide as the shelf (plus room for the icons
        to grow), so clicks outside the dock still reach the windows
        underneath.
        """
        return int(self._size["width"])

    def _compute_layout(self):
        """Icon geometry for the current pointer position.

        The icon sizes are eased towards their targets by _step(), so this
        only works out where the icons sit and how big they want to be.
        """
        gap = self._size["gap"]
        pad_x = self._size["pad_x"]

        width, height = self.content_size()
        if width <= 0:
            width = self.metrics.width or 1366

        sizes = self._sizes

        # centres follow from the sizes, so bigger icons push their
        # neighbours aside exactly like macOS does
        centres = []
        x = 0.0
        for size in sizes:
            centres.append(x + size / 2)
            x += size + gap

        total = centres[-1] + sizes[-1] / 2 if centres else 0
        shelf_w = total + pad_x * 2
        shelf_x = (width - shelf_w) / 2

        shelf_h = self.shelf_height()
        # the shelf sits at the bottom of the surface and slides down into
        # it when the dock hides
        shelf_y = height - shelf_h - self._base_margin + self._offset
        icon_bottom = shelf_y + shelf_h - self._pad_y

        layout = []
        for index, size in enumerate(sizes):
            layout.append({
                "index": index,
                "x": shelf_x + pad_x + centres[index] - size / 2,
                "size": size,
                "centre": shelf_x + pad_x + centres[index],
                "bottom": icon_bottom,
            })
        self._layout = layout
        self._shelf = (shelf_x, shelf_y, shelf_w, shelf_h)
        return layout

    # -- magnification -------------------------------------------------------

    def _magnified(self, pointer_x):
        """Target icon sizes for a pointer position.

        The pointer is measured against the resting dock, so the icons that
        grow also move the ones next to them -- that is what gives macOS
        its elastic feel.
        """
        base = self._size["base"]
        top = self._size["top"]
        gap = self._size["gap"]
        pad_x = self._size["pad_x"]
        count = len(self._sizes)

        width, _ = self.content_size()
        if width <= 0:
            width = self.metrics.width or 1366

        # resting geometry
        centres = []
        x = 0.0
        for _ in range(count):
            centres.append(x + base / 2)
            x += base + gap
        shelf_w = centres[-1] + base / 2 + pad_x * 2 if centres else 0.0
        shelf_x = (width - shelf_w) / 2

        # the pointer in the dock's own coordinate space
        local = pointer_x - (shelf_x + pad_x)

        targets = [base] * count
        for _ in range(2):
            sizes = []
            for index in range(count):
                dist = abs(local - centres[index])
                span = base * GROW_SPAN
                if dist < span:
                    t = 1.0 - dist / span
                    eased = t * t * (3 - 2 * t)
                    sizes.append(base + (top - base) * eased)
                else:
                    sizes.append(base)
            centres = []
            x = 0.0
            for size in sizes:
                centres.append(x + size / 2)
                x += size + gap
            targets = sizes
        return targets

    def _update_targets(self):
        pointer_x = self.pointer[0]
        if pointer_x < 0:
            targets = [self._size["base"]] * len(self._sizes)
        else:
            targets = self._magnified(pointer_x)
        if targets != self._targets:
            self._targets = targets
            self._animate()

    def _animate(self):
        if self._animating:
            return
        self._animating = True
        GLib.timeout_add(16, self._step)

    def _step(self):
        moved = False
        for index, target in enumerate(self._targets):
            current = self._sizes[index]
            if abs(current - target) < 0.4:
                self._sizes[index] = target
            else:
                self._sizes[index] = current + (target - current) * 0.35
                moved = True

        # the launch bounce of an icon that was just started
        if self._bounce >= 0:
            elapsed = time.monotonic() - self._bounce_started
            if elapsed > 1.1:
                self._bounce = -1
            else:
                moved = True

        self.redraw()
        if not moved:
            self._animating = False
            return False
        return True

    def _bounce_offset(self, index):
        """How far the bouncing icon is lifted right now."""
        if self._bounce != index:
            return 0.0
        elapsed = time.monotonic() - self._bounce_started
        if elapsed > 1.1:
            return 0.0
        return abs(math.sin(elapsed * math.pi * 3.2)) * 9 * self.metrics.scale

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()

        layout = self._compute_layout()
        if not layout:
            return

        shelf_x, shelf_y, shelf_w, shelf_h = self._shelf

        draw.glass_panel(
            cr, shelf_x, shelf_y, shelf_w, shelf_h, m.px("dock_radius"), pal,
            exponent=m.squareness, shadow=True, shadow_spread=16,
        )

        for item in layout:
            index = item["index"]
            size = item["size"]
            x = item["x"]
            y = item["bottom"] - size - self._bounce_offset(index)
            app = self._items()[index]

            if app.get("glyph") == "grid":
                draw.fill_squircle(cr, x, y, size, size, size * 0.22,
                                   pal["fill_hover"], m.squareness)
                glyphs.grid(cr, x + size * 0.24, y + size * 0.24,
                            size * 0.52, pal["text"])
            else:
                self._paint_icon(cr, app, x, y, size, pal)

            # running indicator
            if index < len(APPS) and self._is_running(app):
                r = m.px("dock_running_dot") / 2
                draw.fill_squircle(
                    cr, item["centre"] - r, item["bottom"] + m.px("dock_running_gap"),
                    r * 2, r * 2, r, pal["text_dim"], 2.0,
                )

        # a separator before the recent programs and before the trash
        items = self._items()
        for index, item in enumerate(items):
            if index and (item.get("recent") or index == len(items) - 1):
                sep_x = layout[index - 1]["centre"] + layout[index - 1]["size"] / 2
                sep_x += self._size["gap"] * 0.5
                draw.fill_squircle(cr, sep_x, shelf_y + shelf_h * 0.24, 1,
                                   shelf_h * 0.52, 0.5, pal["separator"], 2.0)

        if self.hover >= 0 and self.hover < len(layout):
            self._paint_tooltip(cr, layout[self.hover])

    def _paint_icon(self, cr, app, x, y, size, pal):
        """The icon of an application.

        The icons the shell ships come first, so the dock keeps its own
        look; a program the shell has no icon for takes the icon of the
        desktop, and a program nobody knows gets a tile with its first
        letter on it.
        """
        if draw.draw_icon(cr, app["id"], x, y, size):
            return
        bundled = apps.bundled_icon_for(app.get("app"), app.get("id"))
        if bundled and draw.draw_icon(cr, bundled, x, y, size):
            return
        pixbuf = self._system_icon(app.get("app") or app["id"])
        if pixbuf is None and app.get("recent"):
            pixbuf = self._recent_icon(app)
        if pixbuf is None:
            draw.app_tile(cr, x, y, size, app.get("label") or "", pal,
                          self.metrics.squareness)
            return
        iw, ih = pixbuf.get_width(), pixbuf.get_height()
        factor = size / max(iw, ih)
        cr.save()
        cr.translate(x + (size - iw * factor) / 2, y + (size - ih * factor) / 2)
        cr.scale(factor, factor)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        cr.restore()

    def _system_icon(self, name):
        """The icon the desktop has for an application."""
        if not name:
            return None
        if name in self._icons:
            return self._icons[name]
        path = apps.icon_for_app(name)
        pixbuf = draw.load_icon(path) if path else None
        self._icons[name] = pixbuf
        return pixbuf

    def _recent_icon(self, app):
        """The icon of a program of the recent section.

        The compositor and the desktop files do not always call a
        program the same, so the friendly name is asked as well.
        """
        label = app.get("label") or ""
        if not label:
            return None
        if label in self._icons:
            return self._icons[label]
        path = apps.icon_for_app(label)
        pixbuf = draw.load_icon(path) if path else None
        self._icons[label] = pixbuf
        return pixbuf

    def _paint_tooltip(self, cr, item):
        m = self.metrics
        pal = m.palette()
        app = self._items()[item["index"]]
        label = app["label"]
        font = 11 * m.scale
        pad_x = 9 * m.scale
        pad_y = 5 * m.scale

        text_w = draw.text_width(cr, label, font)
        w = text_w + pad_x * 2
        h = font + pad_y * 2
        x = item["centre"] - w / 2
        y = item["bottom"] - item["size"] - 12 * m.scale - h

        draw.fill_squircle(cr, x, y, w, h, 8 * m.scale, pal["fill_hover"], 2.0)
        draw.stroke_squircle(cr, x, y, w, h, 8 * m.scale, pal["separator"],
                             1.0, 2.0)
        draw.draw_text(cr, x + w / 2, y + h / 2, label, font, pal["text"],
                       align="center", baseline="middle")

    def _is_running(self, app):
        """True when the program of a dock item has a window open.

        The id of a window and the id of a program are not always the
        same: the terminal is "foot" in the dock and "footclient" in the
        compositor, and Code is "code" in the dock and "code-oss" on the
        machine.  The friendly names are what tie them together.
        """
        key = (app.get("app") or app.get("id") or "").lower()
        label = (app.get("label") or "").lower()
        if not key and not label:
            return False
        for running in self._running:
            if key and running == key:
                return True
            friendly = state.friendly_name(running).lower()
            if label and friendly and friendly == label:
                return True
        return False

    def _window_of(self, app):
        """The open window of a dock item."""
        key = (app.get("app") or app.get("id") or "").lower()
        label = (app.get("label") or "").lower()
        for app_id, entry in self._windows.items():
            if key and app_id == key:
                return entry
            friendly = state.friendly_name(app_id).lower()
            if label and friendly and friendly == label:
                return entry
        return None

    # -- visibility ----------------------------------------------------------

    def set_shown(self, shown):
        """Slide the dock in or out of the screen.

        macOS slides the dock down when it hides and pushes it up when the
        pointer reaches the bottom edge.  The surface is never unmapped:
        it only moves, which keeps the animation smooth.
        """
        if shown:
            self.slide_to(0)
        else:
            self.slide_to(self._slide_distance)

    # -- input ---------------------------------------------------------------

    def input_rects(self):
        """Only the shelf takes the pointer.

        The surface is taller than the shelf because the icons grow out of
        it, and those transparent pixels would otherwise swallow the
        clicks of the windows underneath the dock.
        """
        if not self._layout:
            self._compute_layout()
        shelf_x, shelf_y, shelf_w, shelf_h = self._shelf
        if shelf_w <= 0:
            return None
        icon_bottom = shelf_y + shelf_h - self._pad_y
        top = icon_bottom - self._size["top"]
        # the shelf slides out of the surface, and the region with it
        return [(shelf_x, top, shelf_w, icon_bottom - top)]

    def on_motion(self, x, y):
        self._update_targets()
        self.shell.keep_alive("dock")
        for item in self._layout:
            if item["x"] <= x <= item["x"] + item["size"]:
                if self.hover != item["index"]:
                    self.hover = item["index"]
                    self.redraw()
                return False
        if self.hover != -1:
            self.hover = -1
            self.redraw()
        return False

    def on_click(self, x, y, button):
        self._last_click = (round(x), round(y), button)
        for item in self._layout:
            if item["x"] <= x <= item["x"] + item["size"]:
                index = item["index"]
                app = self._items()[index]
                if button == 3:
                    self.shell.open_dock_menu(app, index)
                    return True
                self._activate(app, index)
                return True
        return False

    def activate_index(self, index):
        """Click a dock icon by its number.

        The command fifo uses it to try a dock item out without a mouse.
        """
        items = self._items()
        if 0 <= index < len(items):
            self._activate(items[index], index)
            return True
        return False

    def _activate(self, app, index=-1):
        """Launch an app, or focus it when it is already running.

        Launching a second copy of a running application is what made the
        dock open everything twice; macOS raises the window instead.
        """
        if app.get("special") == "launchpad":
            self.shell.open_launchpad()
            return
        key = (app.get("app") or "").lower()
        entry = self._window_of(app)
        if entry is not None:
            # the program is already open: raise its window instead of
            # starting a second copy of it
            state.raise_window(entry.get("title") or "")
            return
        command = app.get("cmd") or ""
        if not command and key:
            # a program of the recent section: find it on the machine
            for entry in apps.applications():
                if entry["id"].lower() == key or \
                        entry["name"].lower() == key:
                    command = entry["exec"]
                    break
        if not command:
            return
        if not self._installed(command):
            self.shell.show_message(
                app.get("label", "Application"),
                f"{app.get('label', 'This program')} is not installed")
            return
        # the error of a program that refuses to start is worth showing
        error_file = f"/tmp/macshell-launch-{os.getpid()}.err"
        try:
            with open(error_file, "w"):
                pass
        except OSError:
            error_file = "/dev/null"
        state.spawn(f"{command} 2> {error_file}")
        # the icon bounces while the application starts up
        if index < 0:
            index = 0
        self._bounce = index
        self._bounce_started = time.monotonic()
        self._animate()
        GLib.timeout_add(2000, self._report_failure, app, key, error_file)
        GLib.timeout_add(9000, self._report_slow, app, key)

    def _installed(self, command):
        """True when the program of a dock item is on the machine."""
        program = command.split()[0] if command else ""
        if not program:
            return False
        if os.path.isabs(program):
            return os.path.exists(program)
        return shutil.which(program) is not None

    def _report_failure(self, app, key, error_file):
        """Tell the user why an application did not come up.

        Only a program that said something is worth a message: an
        application that is still starting has not failed, and on a slow
        machine it often needs a few seconds to show its first window.
        The line that says what went wrong is the one to show: a program
        that writes a few lines of news before it gives up would
        otherwise report its first line.
        """
        try:
            with open(error_file, encoding="utf-8", errors="replace") as fh:
                lines = [line.strip() for line in fh.read().splitlines()
                         if line.strip()]
        except OSError:
            lines = []
        if not lines:
            return False
        message = ""
        for line in lines:
            if "error" in line.lower() or line.lower().startswith("warning"):
                message = line
                break
        if not message:
            message = lines[-1]
        # the programs say what they do in a prefix, and the message
        # should be about the problem and not about the program
        message = re.sub(r"^(warning|error|info)\s*\([^)]*\):\s*", "",
                         message, flags=re.IGNORECASE)
        message = message[:120]
        self.shell.show_message(app.get("label", "Application"), message)
        return False

    def _report_slow(self, app, key):
        """A program that is still starting after a while."""
        if self._is_running(app):
            return False
        self.shell.show_message(
            app.get("label", "Application"),
            f"{app.get('label', 'The program')} is still starting")
        return False

    def on_leave(self):
        self.hover = -1
        self.pointer = (-1, -1)
        self._update_targets()
        self.shell.panel_left("dock")
        self.redraw()
        return False
