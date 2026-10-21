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

from ..macui import apps, draw, glyphs, state  # noqa: E402
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
        self._groups: list = []
        self._counts: dict = {}
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

    # -- the groups ----------------------------------------------------------

    def _build_groups(self):
        """The open windows, grouped by the program they belong to.

        macOS keeps a group of windows for every program, so the strip
        shows one card per program and the windows of that program come
        forward one after the other.
        """
        groups = []
        index = {}
        for entry in self.shell.toplevel_state():
            app_id = (entry.get("app_id") or "").lower()
            if not app_id:
                continue
            if app_id not in index:
                index[app_id] = len(groups)
                groups.append({
                    "app_id": app_id,
                    "name": state.FRIENDLY_NAMES.get(app_id, app_id),
                    "windows": [],
                    "focused": False,
                })
            group = groups[index[app_id]]
            group["windows"].append(entry.get("title") or "")
            if entry.get("activated"):
                group["focused"] = True
        return groups

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        self._groups = self._build_groups()
        if not self._groups:
            return

        self._cards = []
        for index, group in enumerate(self._groups[:8]):
            x = 0.0
            y = index * (CARD_HEIGHT * scale + GAP * scale)
            focused = group["focused"]
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
            pixbuf = self._icon_for(group["app_id"])
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

            color = pal["on_accent"] if focused else pal["text"]
            draw.draw_text(cr, x + 12 * scale + icon + 8 * scale,
                           y + 24 * scale, group["name"], 10 * scale,
                           color, weight="bold", baseline="middle",
                           max_width=width - icon - 30 * scale, ellipsize=True)
            count = len(group["windows"])
            detail = (group["windows"][0] if count == 1
                      else f"{count} windows")
            draw.draw_text(cr, x + 12 * scale + icon + 8 * scale,
                           y + 46 * scale, detail, 9 * scale,
                           pal["on_accent"] if focused else pal["text_dim"],
                           baseline="middle", max_width=width - icon - 30 * scale,
                           ellipsize=True)

            self._cards.append((x, y, width, CARD_HEIGHT * scale, group))

    def _icon_for(self, app_id):
        if not app_id:
            return None
        path = apps.icon_path(app_id)
        if not path:
            return None
        return draw.load_icon(path)

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
        for cx, cy, cw, ch, group in self._cards:
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                self._raise(group)
                self.close()
                return True
        self.close()
        return True

    def _raise(self, group):
        """Bring the next window of the group to the front."""
        titles = group.get("windows") or []
        if not titles:
            return
        count = self._counts.get(group["app_id"], 0)
        self._counts[group["app_id"]] = count + 1
        self.shell.activate_window(titles[count % len(titles)])
