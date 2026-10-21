"""The Tahoe dock.

A floating glass shelf of app icons that magnifies under the pointer the way
macOS does: neighbouring icons ease apart and grow, running apps carry a
small indicator dot and the hovered app shows a label bubble.
"""

from __future__ import annotations

import json
import math
import os
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
    {"id": "chromium", "label": "Chromium", "cmd": "chromium", "app": "chromium"},
    {"id": "dolphin", "label": "Files", "cmd": "dolphin", "app": "dolphin"},
    {"id": "yazi", "label": "Yazi", "cmd": "yazi", "app": "yazi"},
    {"id": "terminal", "label": "Terminal", "cmd": "foot", "app": "foot"},
    {"id": "ghostty", "label": "Ghostty", "cmd": "ghostty", "app": "ghostty"},
    {"id": "vscode", "label": "Visual Studio Code", "cmd": "code", "app": "code"},
    {"id": "gimp", "label": "GIMP", "cmd": "gimp", "app": "gimp"},
    {"id": "mpv", "label": "mpv", "cmd": "mpv", "app": "mpv"},
    {"id": "vlc", "label": "VLC", "cmd": "vlc", "app": "vlc"},
    {"id": "audacity", "label": "Audacity", "cmd": "audacity", "app": "audacity"},
    {"id": "obs", "label": "OBS Studio", "cmd": "obs", "app": "obs"},
    {"id": "spotify", "label": "Spotify", "cmd": "spotify", "app": "spotify"},
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
    if not isinstance(saved, list):
        return list(DEFAULT_APPS)
    apps = []
    for entry in saved:
        for known in DEFAULT_APPS:
            if known["id"] == entry:
                apps.append(dict(known))
                break
    return apps


def _save_apps(apps):
    try:
        os.makedirs(os.path.dirname(DOCK_CONFIG), exist_ok=True)
        with open(DOCK_CONFIG, "w") as fh:
            json.dump([app["id"] for app in apps], fh, indent=4)
    except OSError:
        pass


APPS = _load_apps()

TRASH = {"id": "trash", "label": "Trash", "cmd": "dolphin trash:///"}

TOOLTIP_SPACE = 30


class Dock(Panel):
    NAMESPACE = "mac-dock"

    def __init__(self, metrics, shell):
        m = metrics
        # the surface starts off screen and slides in when it is wanted
        self._base_margin = int(m.px("dock_margin_bottom"))
        self._hidden_margin = self._base_margin - self.panel_height(metrics)
        super().__init__(
            metrics,
            layer="top",
            anchors={"bottom": True},
            margins={"bottom": self._hidden_margin},
            exclusive=0,
        )
        self.shell = shell
        self.hover = -1
        self._layout: list = []
        self._shelf = (0, 0, 0, 0)
        self._sizes = [metrics.px("dock_icon")] * (len(APPS) + 1)
        self._targets = list(self._sizes)
        self._animating = False
        self._bounce = -1
        self._bounce_started = 0.0
        self._icons: dict = {}

        width = self.panel_width()
        self.set_content_size(width, self.panel_height())
        screen = metrics.width or width
        self.set_horizontal_offset(int((screen - width) / 2))
        self._running = self._detect_running()

    # -- running apps --------------------------------------------------------

    def _detect_running(self):
        """App ids of the windows that are currently open."""
        try:
            return state.running_app_ids()
        except Exception:
            return set()

    def refresh_running(self):
        self._running = self._detect_running()
        self.redraw()

    def reload_apps(self):
        """Pick up a changed list of dock items."""
        global APPS
        APPS = _load_apps()
        count = len(APPS) + 1
        self._sizes = [self.metrics.px("dock_icon")] * count
        self._targets = list(self._sizes)
        self.set_content_size(self.panel_width(), self.panel_height())
        self.redraw()

    # -- geometry ------------------------------------------------------------

    def panel_height(self, m=None):
        m = m or self.metrics
        shelf_h = m.px("dock_icon") + m.px("dock_pad_y") * 2
        return int(shelf_h + (m.px("dock_icon_max") - m.px("dock_icon"))
                   + TOOLTIP_SPACE)

    def panel_width(self):
        """Width of the dock surface.

        The surface is only as wide as the shelf (plus room for the icons
        to grow), so clicks outside the dock still reach the windows
        underneath.
        """
        m = self.metrics
        base = m.px("dock_icon")
        gap = m.px("dock_gap")
        pad = m.px("dock_pad_x")
        count = len(APPS) + 1
        resting = base * count + gap * (count - 1)
        return int(resting + pad * 2 + m.px("dock_icon_max") * 0.6)

    def shelf_height(self):
        m = self.metrics
        return m.px("dock_icon") + m.px("dock_pad_y") * 2

    def _compute_layout(self):
        """Icon geometry for the current pointer position.

        The icon sizes are eased towards their targets by _step(), so this
        only works out where the icons sit and how big they want to be.
        """
        m = self.metrics
        base = m.px("dock_icon")
        gap = m.px("dock_gap")
        pad_x = m.px("dock_pad_x")

        width, height = self.content_size()
        if width <= 0:
            width = m.width or 1366

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
        # the shelf sits at the bottom of the surface; the surface itself
        # stops short of the bottom edge of the screen, so the strip that
        # brings the dock back is never covered by it
        shelf_y = height - shelf_h
        icon_bottom = shelf_y + shelf_h - m.px("dock_pad_y")

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
        m = self.metrics
        base = m.px("dock_icon")
        top = m.px("dock_icon_max")
        gap = m.px("dock_gap")
        pad_x = m.px("dock_pad_x")
        count = len(APPS) + 1

        width, _ = self.content_size()
        if width <= 0:
            width = m.width or 1366

        # resting geometry
        centres = []
        x = 0.0
        for _ in range(count):
            centres.append(x + base / 2)
            x += base + gap
        shelf_w = centres[-1] + base / 2 + pad_x * 2
        shelf_x = (width - shelf_w) / 2

        # the pointer in the dock's own coordinate space
        local = pointer_x - (shelf_x + pad_x)

        targets = [base] * count
        for _ in range(2):
            sizes = []
            for index in range(count):
                dist = abs(local - centres[index])
                span = base * 2.2
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
        m = self.metrics
        pointer_x = self.pointer[0]
        if pointer_x < 0:
            targets = [m.px("dock_icon")] * (len(APPS) + 1)
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
            app = APPS[index] if index < len(APPS) else TRASH

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

        # separator before the trash
        sep_x = layout[-2]["centre"] + layout[-2]["size"] / 2
        sep_x += m.px("dock_gap") * 0.5
        draw.fill_squircle(cr, sep_x, shelf_y + shelf_h * 0.24, 1,
                           shelf_h * 0.52, 0.5, pal["separator"], 2.0)

        if self.hover >= 0 and self.hover < len(layout):
            self._paint_tooltip(cr, layout[self.hover])

    def _paint_icon(self, cr, app, x, y, size, pal):
        """The icon of an application.

        The shell ships a few icons, but anything else takes the icon the
        system has for the application, so a new program in the dock
        looks right straight away.
        """
        if draw.draw_icon(cr, app["id"], x, y, size):
            return
        pixbuf = self._system_icon(app.get("app") or app["id"])
        if pixbuf is None:
            draw.fill_squircle(cr, x + size * 0.18, y + size * 0.1,
                               size * 0.64, size * 0.7, size * 0.1,
                               pal["fill_hover"], self.metrics.squareness)
            glyphs.grid(cr, x + size * 0.3, y + size * 0.2, size * 0.4,
                        pal["text_dim"])
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
        pixbuf = None
        path = apps.icon_path(name)
        if path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            except Exception:  # noqa: BLE001
                pixbuf = None
        self._icons[name] = pixbuf
        return pixbuf

    def _paint_tooltip(self, cr, item):
        m = self.metrics
        pal = m.palette()
        app = APPS[item["index"]] if item["index"] < len(APPS) else TRASH
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
        key = (app.get("app") or "").lower()
        if not key or not self._running:
            return False
        for running in self._running:
            if running == key or key in running or running in key:
                return True
        return False

    # -- visibility ----------------------------------------------------------

    def set_shown(self, shown):
        """Slide the dock in or out of the screen.

        macOS slides the dock down when it hides and pushes it up when the
        pointer reaches the bottom edge.  The surface is never unmapped:
        it only moves, which keeps the animation smooth.
        """
        if shown:
            self.slide("bottom", self._base_margin)
        else:
            self.slide("bottom", self._hidden_margin)

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
        m = self.metrics
        icon_bottom = shelf_y + shelf_h - m.px("dock_pad_y")
        top = icon_bottom - m.px("dock_icon_max")
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
        for item in self._layout:
            if item["x"] <= x <= item["x"] + item["size"]:
                index = item["index"]
                app = APPS[index] if index < len(APPS) else TRASH
                if button == 3:
                    self.shell.open_dock_menu(app, index)
                    return True
                self._activate(app, index)
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
        if key and self._is_running(app):
            if state.activate_app(key):
                return
        state.spawn(app["cmd"])
        # the icon bounces while the application starts up
        if index < 0:
            index = 0
        self._bounce = index
        self._bounce_started = time.monotonic()
        self._animate()

    def on_leave(self):
        self.hover = -1
        self.pointer = (-1, -1)
        self._update_targets()
        self.shell.panel_left("dock")
        self.redraw()
        return False
