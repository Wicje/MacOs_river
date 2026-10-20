"""Desktop icons.

macOS Sonoma can show the files of the desktop as icons in the top left
corner.  This panel does the same: the files of ~/Desktop are listed in a
column, double clicking one opens it.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf  # noqa: E402

from ..macui import draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ICON = 48
GAP = 12
MAX_ITEMS = 12


class DesktopIcons(Panel):
    NAMESPACE = "mac-desktop-icons"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="bottom",
            anchors={"top": True, "left": True},
            margins={"top": int(metrics.px("menu_bar_height")) + 12, "left": 12},
            keyboard=False,
        )
        self.shell = shell
        self._items: list = []
        self._icons: dict = {}
        self.set_content_size(int(metrics.px("ICON") if False else 64),
                              int(64 * 12))

    # -- state ---------------------------------------------------------------

    def refresh(self):
        directory = os.path.expanduser("~/Desktop")
        items = []
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            names = []
        for name in names:
            if name.startswith("."):
                continue
            items.append((name, os.path.join(directory, name)))
            if len(items) >= MAX_ITEMS:
                break
        self._items = items
        self.set_content_size(int(64 * self.metrics.scale),
                              int((ICON + GAP) * self.metrics.scale *
                                  max(len(items), 1)))
        self.redraw()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        size = ICON * m.scale
        gap = GAP * m.scale
        y = 0.0

        for name, path in self._items:
            x = 0.0
            pixbuf = self._icon_for(path)
            if pixbuf is not None:
                iw, ih = pixbuf.get_width(), pixbuf.get_height()
                scale = size / max(iw, ih)
                cr.save()
                cr.translate(x + (size - iw * scale) / 2, y + (size - ih * scale) / 2)
                cr.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x + size * 0.18, y + size * 0.1,
                                   size * 0.64, size * 0.7, size * 0.1,
                                   pal["fill_hover"], m.squareness)
                glyphs.grid(cr, x + size * 0.3, y + size * 0.2, size * 0.4,
                            pal["text_dim"])

            draw.draw_text(cr, x + size / 2, y + size + 10 * m.scale, name,
                           10 * m.scale, pal["text"], align="center",
                           baseline="middle", max_width=size + 24 * m.scale,
                           ellipsize=True, shadow=(0, 0, 0, 0.55))
            y += size + gap + 14 * m.scale

    def _icon_for(self, path):
        if path in self._icons:
            return self._icons[path]
        pixbuf = None
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
            candidate = path + suffix
            if not os.path.exists(candidate):
                continue
            try:
                if candidate.endswith(".svg"):
                    from gi.repository import GdkPixbuf  # noqa: F401
                    pixbuf = None
                else:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(candidate)
            except Exception:
                pixbuf = None
            if pixbuf is not None:
                break
        self._icons[path] = pixbuf
        return pixbuf

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        m = self.metrics
        size = ICON * m.scale
        gap = GAP * m.scale
        row = size + gap + 14 * m.scale
        index = int(y // row)
        if 0 <= index < len(self._items):
            name, path = self._items[index]
            if os.path.isdir(path):
                subprocess.Popen(["dolphin", path], start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", path], start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            return True
        return False
