"""The application switcher.

macOS shows a row of application icons in the middle of the screen when
the command key is held.  This is the same idea as a clickable overlay:
the running applications in a row, the focused one highlighted.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ICON = 56
GAP = 18


class Switcher(Panel):
    NAMESPACE = "mac-switcher"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True, "right": True, "bottom": True},
            keyboard=False,
        )
        self.shell = shell
        self._items: list = []
        self._icons: dict = {}
        self.hover = -1

    # -- lifecycle -----------------------------------------------------------

    def open(self):
        self._items = self._collect()
        self.show_all()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self):
        if self.get_visible():
            self.close()
        else:
            self.open()

    def _collect(self):
        """The running applications, the focused one first."""
        running = {}
        focused = ""
        for app_id, title in self.shell.window_list():
            key = (app_id or "").lower()
            if not key:
                continue
            running.setdefault(key, title)
        for entry in self.shell.toplevel_state():
            if entry.get("activated"):
                focused = (entry.get("app_id") or "").lower()
        items = []
        for key, title in running.items():
            items.append({"app_id": key, "title": title, "focused": key == focused})
        items.sort(key=lambda item: (not item["focused"], item["app_id"]))
        return items[:10]

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        # a soft panel behind the row
        if self._items:
            icon = ICON * scale
            gap = GAP * scale
            row_w = len(self._items) * (icon + gap) - gap
            x = (width - row_w) / 2
            y = (height - (icon + 40 * scale)) / 2
            draw.fill_squircle(cr, x - 24 * scale, y - 22 * scale,
                               row_w + 48 * scale, icon + 62 * scale,
                               18 * scale, (*pal["menu_bar"][:3], 0.9),
                               m.squareness)

            self._cells = []
            for index, item in enumerate(self._items):
                cx = x + index * (icon + gap)
                pixbuf = self._icon_for(item["app_id"])
                if pixbuf is not None:
                    iw, ih = pixbuf.get_width(), pixbuf.get_height()
                    factor = icon / max(iw, ih)
                    cr.save()
                    cr.translate(cx + (icon - iw * factor) / 2,
                                 y + (icon - ih * factor) / 2)
                    cr.scale(factor, factor)
                    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                    cr.paint()
                    cr.restore()
                else:
                    draw.fill_squircle(cr, cx, y, icon, icon, icon * 0.22,
                                       pal["fill_hover"], m.squareness)
                    glyphs.grid(cr, cx + icon * 0.26, y + icon * 0.26,
                                icon * 0.48, pal["text"])

                if item["focused"] or self.hover == index:
                    draw.stroke_squircle(cr, cx - 4 * scale, y - 4 * scale,
                                         icon + 8 * scale, icon + 8 * scale,
                                         (icon + 8 * scale) / 2,
                                         pal["accent"], 2.0, m.squareness)
                draw.draw_text(cr, cx + icon / 2, y + icon + 16 * scale,
                               item["app_id"], 10 * scale, pal["text_dim"],
                               align="center", baseline="middle",
                               max_width=icon + 20 * scale, ellipsize=True)
                self._cells.append((cx, y, icon, index))

    def _icon_for(self, app_id):
        if app_id in self._icons:
            return self._icons[app_id]
        path = apps.icon_path(app_id)
        pixbuf = draw.load_icon(path) if path else None
        self._icons[app_id] = pixbuf
        return pixbuf

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        found = -1
        for index, (cx, cy, size, _item) in enumerate(getattr(self, "_cells", [])):
            if cx <= x <= cx + size and cy <= y <= cy + size:
                found = index
                break
        if found != self.hover:
            self.hover = found
            self.redraw()
        return False

    def on_click(self, x, y, button):
        for cx, cy, size, index in getattr(self, "_cells", []):
            if cx <= x <= cx + size and cy <= y <= cy + size:
                item = self._items[index]
                self.shell.activate_app(item["app_id"])
                self.close()
                return True
        self.close()
        return True
