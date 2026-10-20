"""Quick Look and Get Info.

Quick Look shows a preview of a file the way macOS does, and Get Info
shows what the system knows about it.
"""

from __future__ import annotations

import datetime
import mimetypes
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from ..macui import draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

WIDTH = 520
HEIGHT = 420
PREVIEW = 300


def _human(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


class QuickLook(Panel):
    """A floating window with a preview or the file information."""

    NAMESPACE = "mac-quicklook"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=False,
        )
        self.shell = shell
        self.mode = "look"
        self.path = ""
        self._meta = []
        self._text = []
        width = int(WIDTH * metrics.scale)
        height = int(HEIGHT * metrics.scale)
        screen_w = metrics.width or 1366
        screen_h = metrics.height or 768
        self.set_content_size(width, height)
        self.set_position(int((screen_w - width) / 2),
                          int((screen_h - height) / 2))

    # -- lifecycle -----------------------------------------------------------

    def show_file(self, path, mode="look"):
        self.path = path
        self.mode = mode
        self._meta = []
        self._text = []
        try:
            stat = os.stat(path)
            kind = mimetypes.guess_type(path)[0] or "unknown"
            self._meta = [
                ("Kind", kind),
                ("Size", _human(stat.st_size)),
                ("Created", datetime.datetime.fromtimestamp(stat.st_ctime)
                 .strftime("%d %b %Y, %H:%M")),
                ("Modified", datetime.datetime.fromtimestamp(stat.st_mtime)
                 .strftime("%d %b %Y, %H:%M")),
                ("Where", os.path.dirname(path)),
            ]
        except OSError:
            self._meta = [("Kind", "unknown")]

        if mode == "look" and path.lower().endswith((".txt", ".md", ".log",
                                                     ".sh", ".py", ".json",
                                                     ".ini", ".conf")):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self._text = fh.read().splitlines()[:20]
            except OSError:
                self._text = []

        self.show_all()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self, path, mode="look"):
        if self.get_visible() and self.path == path and self.mode == mode:
            self.close()
        else:
            self.show_file(path, mode)

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, 12 * scale)
        cr.clip()
        dark = m.config.get("theme", "dark") == "dark"
        cr.set_source_rgba(0.09, 0.09, 0.11, 0.98 if dark else 0.99)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.restore()
        draw.stroke_squircle(cr, 0, 0, width, height, 12 * scale,
                             pal["separator"], 1.0, m.squareness)

        title = os.path.basename(self.path) or "Quick Look"
        draw.draw_text(cr, 18 * scale, 22 * scale, title,
                       m.font("menu_font_size"), pal["text"], weight="bold",
                       baseline="middle", max_width=width - 60 * scale,
                       ellipsize=True)
        draw.draw_text(cr, width - 18 * scale, 22 * scale, "esc", 10 * scale,
                       pal["text_faint"], align="right", baseline="middle")

        if self.mode == "info":
            self._paint_info(cr, width, height, scale, pal)
        else:
            self._paint_preview(cr, width, height, scale, pal)

    def _paint_preview(self, cr, width, height, scale, pal):
        x = 16 * scale
        y = 44 * scale
        box_w = width - 32 * scale
        box_h = height - 100 * scale

        draw.fill_squircle(cr, x, y, box_w, box_h, 8 * scale, pal["fill"],
                           self.metrics.squareness)

        pixbuf = None
        if self.path.lower().endswith((".png", ".jpg", ".jpeg", ".webp",
                                       ".gif", ".bmp")):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.path)
            except Exception:
                pixbuf = None

        if pixbuf is not None:
            iw, ih = pixbuf.get_width(), pixbuf.get_height()
            factor = min(box_w / iw, box_h / ih, 1.0)
            cr.save()
            cr.translate(x + (box_w - iw * factor) / 2,
                         y + (box_h - ih * factor) / 2)
            cr.scale(factor, factor)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint()
            cr.restore()
        elif self._text:
            for index, line in enumerate(self._text[:12]):
                draw.draw_text(cr, x + 12 * scale, y + 16 * scale + index * 16 * scale,
                               line[:48], 11 * scale, pal["text_dim"],
                               baseline="middle")
        else:
            glyphs.grid(cr, x + box_w / 2 - 24 * scale, y + box_h / 2 - 24 * scale,
                        48 * scale, pal["text_faint"])
            draw.draw_text(cr, x + box_w / 2, y + box_h / 2 + 40 * scale,
                           "No preview available", 11 * scale,
                           pal["text_faint"], align="center", baseline="middle")

        # the buttons at the bottom
        by = height - 44 * scale
        for index, (label, action) in enumerate((
                ("Open", self._open), ("Get Info", self._info))):
            bw = 88 * scale
            bx = 16 * scale + index * (bw + 10 * scale)
            draw.fill_squircle(cr, bx, by, bw, 26 * scale, 13 * scale,
                               pal["fill_hover"], 2.0)
            draw.draw_text(cr, bx + bw / 2, by + 13 * scale, label,
                           11 * scale, pal["text"], align="center",
                           baseline="middle")
            self._buttons = getattr(self, "_buttons", [])
            self._buttons.append((bx, by, bw, 26 * scale, action))

    def _paint_info(self, cr, width, height, scale, pal):
        x = 18 * scale
        y = 52 * scale
        for label, value in self._meta:
            draw.draw_text(cr, x, y, label, 11 * scale, pal["text_faint"],
                           baseline="middle")
            draw.draw_text(cr, x + 96 * scale, y, value, 11 * scale, pal["text"],
                           baseline="middle", max_width=width - 130 * scale,
                           ellipsize=True)
            y += 24 * scale

    # -- actions -------------------------------------------------------------

    def _open(self):
        subprocess.Popen(["xdg-open", self.path], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    def _info(self):
        self.show_file(self.path, "info")

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        for bx, by, bw, bh, action in getattr(self, "_buttons", []):
            if bx <= x <= bx + bw and by <= y <= by + bh:
                action()
                return True
        self.close()
        return True
