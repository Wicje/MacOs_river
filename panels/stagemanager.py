"""Stage Manager.

macOS keeps a strip of window groups along the left edge of the screen
and slides the other windows out of the way.  This is the strip: every
open window as a small card, the focused one highlighted.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

CARD_WIDTH = 150
CARD_HEIGHT = 92
GAP = 10
MARGIN = 10


class StageManager(Panel):
    NAMESPACE = "mac-stage-manager"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            margins={"top": int(metrics.px("menu_bar_height")) + 12,
                     "left": MARGIN},
            keyboard=False,
        )
        self.shell = shell
        self._cards: list = []
        self.hover = -1
        self.set_content_size(int(CARD_WIDTH * metrics.scale),
                              int(CARD_HEIGHT * metrics.scale))

    # -- lifecycle -----------------------------------------------------------

    def refresh(self):
        self.set_content_size(int(CARD_WIDTH * self.metrics.scale),
                              int(CARD_HEIGHT * self.metrics.scale))
        self.redraw()

    def open(self):
        self.show_all()
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
        scale = m.scale

        windows = self.shell.toplevel_state()
        if not windows:
            return

        self._cards = []
        for index, entry in enumerate(windows[:8]):
            x = 0.0
            y = index * (CARD_HEIGHT * scale + GAP * scale)
            focused = entry.get("activated")
            hovered = self.hover == index

            draw.fill_squircle(cr, x, y, width, CARD_HEIGHT * scale,
                               10 * scale,
                               pal["accent"] if focused
                               else (pal["fill_hover"] if hovered
                                     else pal["fill"]),
                               m.squareness)
            draw.stroke_squircle(cr, x, y, width, CARD_HEIGHT * scale,
                                 10 * scale, pal["separator"], 1.0,
                                 m.squareness)

            icon = 28 * scale
            pixbuf = self._icon_for(entry.get("app_id") or "")
            if pixbuf is not None:
                iw, ih = pixbuf.get_width(), pixbuf.get_height()
                factor = icon / max(iw, ih)
                cr.save()
                cr.translate(x + 12 * scale + (icon - iw * factor) / 2,
                             y + 12 * scale + (icon - ih * factor) / 2)
                cr.scale(factor, factor)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x + 12 * scale, y + 12 * scale, icon, icon,
                                   icon * 0.24, pal["fill_hover"],
                                   m.squareness)
                glyphs.grid(cr, x + 12 * scale + icon * 0.26,
                            y + 12 * scale + icon * 0.26, icon * 0.48,
                            pal["text"])

            draw.draw_text(cr, x + 12 * scale + icon + 8 * scale,
                           y + 22 * scale, entry.get("app_id") or "",
                           10 * scale,
                           pal["on_accent"] if focused else pal["text_dim"],
                           baseline="middle", max_width=width - icon - 30 * scale,
                           ellipsize=True)
            draw.draw_text(cr, x + 12 * scale, y + 52 * scale,
                           entry.get("title") or "", 10 * scale,
                           pal["on_accent"] if focused else pal["text_dim"],
                           baseline="middle", max_width=width - 24 * scale,
                           ellipsize=True)

            self._cards.append((x, y, width, CARD_HEIGHT * scale,
                                 entry.get("title") or ""))

    def _icon_for(self, app_id):
        if not app_id:
            return None
        path = apps.icon_path(app_id)
        if not path:
            return None
        try:
            return GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:
            return None

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
