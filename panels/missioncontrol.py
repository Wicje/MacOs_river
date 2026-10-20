"""Mission Control.

An overview of every open window, laid out as cards the way macOS shows
them.  Clicking a card raises that window.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

_icons = {}


def _icon_for(app_id):
    """The icon of an application, looked up once and cached."""
    if not app_id:
        return None
    if app_id in _icons:
        return _icons[app_id]
    path = apps.icon_path(app_id)
    pixbuf = None
    if path:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:
            pixbuf = None
    _icons[app_id] = pixbuf
    return pixbuf


CARD_WIDTH = 190
CARD_HEIGHT = 104
GAP = 18


class MissionControl(Panel):
    NAMESPACE = "mac-mission-control"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True, "right": True, "bottom": True},
            keyboard=False,
        )
        self.shell = shell
        self._cards: list = []
        self.hover = -1
        self._entry = Gtk.Entry()
        self._entry.set_can_focus(True)
        self._entry.set_no_show_all(True)
        self.add(self._entry)

    # -- lifecycle -----------------------------------------------------------

    def open(self):
        self.show_all()
        self._entry.grab_focus()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self):
        if self.get_visible():
            self.close()
        else:
            self.open()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()

        cr.set_source_rgba(0.02, 0.02, 0.03, 0.55)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        windows = self.shell.window_list()
        if not windows:
            draw.draw_text(cr, width / 2, height / 2, "No open windows",
                           m.font("menu_font_size") * 1.4, pal["text_dim"],
                           align="center", baseline="middle")
            self._cards = []
            return

        card_w = CARD_WIDTH * m.scale
        card_h = CARD_HEIGHT * m.scale
        gap = GAP * m.scale

        columns = max(1, min(int((width - gap) / (card_w + gap)), len(windows)))
        rows = (len(windows) + columns - 1) // columns
        left = (width - columns * (card_w + gap) + gap) / 2
        top = max(70 * m.scale, (height - rows * (card_h + gap)) / 2)

        self._cards = []
        for index, (app_id, title) in enumerate(windows):
            col = index % columns
            row = index // columns
            x = left + col * (card_w + gap)
            y = top + row * (card_h + gap)
            self._cards.append((x, y, card_w, card_h, title))

            hovered = self.hover == index
            draw.fill_squircle(cr, x, y, card_w, card_h, 12 * m.scale,
                               pal["fill_hover"] if hovered else pal["fill"],
                               m.squareness)
            draw.stroke_squircle(cr, x, y, card_w, card_h, 12 * m.scale,
                                 pal["separator"], 1.0, m.squareness)

            icon = 40 * m.scale
            pixbuf = _icon_for(app_id)
            if pixbuf is not None:
                iw, ih = pixbuf.get_width(), pixbuf.get_height()
                scale = icon / max(iw, ih)
                cr.save()
                cr.translate(x + 14 * m.scale + (icon - iw * scale) / 2,
                             y + 14 * m.scale + (icon - ih * scale) / 2)
                cr.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x + 14 * m.scale, y + 14 * m.scale,
                                   icon, icon, icon * 0.22, pal["fill_hover"],
                                   m.squareness)
                glyphs.grid(cr, x + 14 * m.scale + icon * 0.26,
                            y + 14 * m.scale + icon * 0.26, icon * 0.48,
                            pal["text"])

            draw.draw_text(cr, x + 14 * m.scale + icon + 12 * m.scale,
                           y + card_h * 0.38, app_id or "Window",
                           m.font("menu_font_size"), pal["text"],
                           weight="bold", baseline="middle",
                           max_width=card_w - icon - 40 * m.scale,
                           ellipsize=True)
            draw.draw_text(cr, x + 14 * m.scale + icon + 12 * m.scale,
                           y + card_h * 0.62, title or "",
                           m.font("cc_font_size"), pal["text_dim"],
                           baseline="middle",
                           max_width=card_w - icon - 40 * m.scale,
                           ellipsize=True)

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        found = -1
        for index, (cx, cy, cw, ch, _title) in enumerate(self._cards):
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                found = index
                break
        if found != self.hover:
            self.hover = found
            self.redraw()
        return False

    def on_click(self, x, y, button):
        for cx, cy, cw, ch, title in self._cards:
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                self.shell.activate_window(title)
                self.close()
                return True
        self.close()
        return True
