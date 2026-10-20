"""The notch.

macOS 26 turns the hardware notch into a panel: a black card hanging from
the top centre of the screen that carries the media widget on the left, a
round shortcut button in the middle and the clock on the right.
"""

from __future__ import annotations

import math
import os
import subprocess
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ART_CACHE = "/tmp/macshell-art"
NIGHTLIGHT = os.path.expanduser("~/.config/river/nightlight.py")


def _playerctl(command):
    subprocess.Popen(["playerctl", command], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


class Notch(Panel):
    NAMESPACE = "mac-notch"

    def __init__(self, metrics, shell):
        width = int(metrics.px("notch_width"))
        height = int(metrics.px("notch_height"))
        super().__init__(
            metrics,
            layer="top",
            anchors={"top": True},
            keyboard=False,
        )
        self.shell = shell
        self.set_content_size(width, height)
        screen = metrics.width or 1366
        self.set_horizontal_offset(int((screen - width) / 2))
        self._media = None
        self._art = None
        self._art_url = None
        self._buttons: list = []

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._media = state.now_playing()
        self._load_art()
        self.redraw()

    def _load_art(self):
        if not self._media:
            return
        url = self._media[5]
        if not url or url == self._art_url:
            return
        self._art_url = url
        path = None
        if url.startswith("file://"):
            path = url[7:]
        elif url.startswith("http"):
            path = f"{ART_CACHE}.img"
            subprocess.run(["curl", "-fsSL", "--max-time", "4", url, "-o", path],
                           capture_output=True)
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                self._art = GdkPixbuf.Pixbuf.new_from_file(path)
            except Exception:
                self._art = None

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        radius = m.px("notch_radius")

        # the card: a black rounded rectangle hanging from the top edge
        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, radius)
        cr.clip()
        grad = cairo.LinearGradient(0, 0, 0, height)
        grad.add_color_stop_rgba(0.0, 0.03, 0.03, 0.04, 1.0)
        grad.add_color_stop_rgba(1.0, 0.06, 0.06, 0.08, 0.98)
        cr.set_source(grad)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.restore()

        self._buttons = []
        pad = m.px("notch_pad")
        art = m.px("notch_art")

        # -- left: the media widget, or the calendar when nothing plays
        x = pad
        if not self._media:
            self._paint_calendar(cr, x, 10 * m.scale, 118 * m.scale,
                                 height - 20 * m.scale, pal)
        if self._media:
            title, artist, status, position, length, _ = self._media
            if self._art is not None:
                pw, ph = self._art.get_width(), self._art.get_height()
                scale = art / max(pw, ph)
                cr.save()
                cr.translate(x, (height - art) / 2)
                cr.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(cr, self._art, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x, (height - art) / 2, art, art, 8,
                                   pal["fill_hover"], m.squareness)
                glyphs.speaker(cr, x + art * 0.26, (height - art * 0.44) / 2,
                               art * 0.48, pal["text_dim"])
            x += art + 12 * m.scale

            text_w = 132 * m.scale
            draw.draw_text(cr, x, height * 0.36, title, m.font("notch_font_size"),
                           pal["text"], weight="bold", baseline="middle",
                           max_width=text_w, ellipsize=True)
            if artist:
                draw.draw_text(cr, x, height * 0.62, artist,
                               m.font("notch_font_size") * 0.85,
                               pal["text_faint"], baseline="middle",
                               max_width=text_w, ellipsize=True)

            # playback controls, the way the notch shows them
            bx = x + text_w + 14 * m.scale
            for action, shape in (("previous", "back"), ("play-pause", "play"),
                                  ("next", "forward")):
                self._paint_button(cr, bx, (height - 14 * m.scale) / 2,
                                   14 * m.scale, shape, pal)
                self._buttons.append((action, bx - 4 * m.scale,
                                      (height - 22 * m.scale) / 2,
                                      22 * m.scale))
                bx += 24 * m.scale

        # -- middle: a round shortcut ------------------------------------
        mid_x = width * 0.62
        button = 34 * m.scale
        cr.save()
        cr.set_source_rgba(*pal["fill_hover"])
        cr.arc(mid_x, height / 2 - 4 * m.scale, button / 2, 0, 2 * math.pi)
        cr.fill()
        cr.restore()
        glyphs.moon(cr, mid_x - 9 * m.scale, height / 2 - 4 * m.scale - 9 * m.scale,
                    18 * m.scale, pal["text"])
        draw.draw_text(cr, mid_x, height - 8 * m.scale, "Night Shift",
                       8.5 * m.scale, pal["text_faint"], align="center",
                       baseline="middle")
        self._buttons.append(("nightlight", mid_x - button / 2,
                              height / 2 - 4 * m.scale - button / 2, button))

        # -- right: the clock --------------------------------------------
        now = time.localtime()
        right = width - pad
        draw.draw_text(cr, right, height * 0.38, time.strftime("%H:%M", now),
                       m.font("notch_font_size") * 1.5, pal["text"],
                       align="right", baseline="middle")
        draw.draw_text(cr, right, height * 0.64, time.strftime("%a %-d %b", now),
                       m.font("notch_font_size") * 0.85, pal["text_faint"],
                       align="right", baseline="middle")

        # separators
        for sep_x in (width * 0.50, width * 0.72):
            cr.set_source_rgba(*pal["separator"])
            cr.rectangle(sep_x, height * 0.22, 1, height * 0.56)
            cr.fill()

    def _paint_calendar(self, cr, x, y, w, h, pal):
        """The little calendar the notch shows when nothing is playing."""
        import datetime

        m = self.metrics
        today = datetime.date.today()
        draw.draw_text(cr, x, y + h * 0.18, today.strftime("%a").upper(),
                       h * 0.20, pal["text_faint"], weight="bold",
                       baseline="middle")
        draw.draw_text(cr, x, y + h * 0.56, str(today.day),
                       h * 0.52, pal["text"], weight="bold",
                       baseline="middle")
        draw.draw_text(cr, x, y + h * 0.86, today.strftime("%B %Y"),
                       h * 0.19, pal["text_faint"], baseline="middle")

    def _paint_button(self, cr, x, y, size, shape, pal):
        color = pal["text_dim"]
        cr.save()
        cr.set_source_rgba(*color)
        if shape == "play":
            cr.move_to(x + size * 0.28, y)
            cr.line_to(x + size * 0.28, y + size)
            cr.line_to(x + size * 0.85, y + size / 2)
            cr.close_path()
            cr.fill()
        elif shape == "back":
            cr.move_to(x + size * 0.72, y)
            cr.line_to(x + size * 0.72, y + size)
            cr.line_to(x + size * 0.10, y + size / 2)
            cr.close_path()
            cr.fill()
            cr.rectangle(x + size * 0.02, y, size * 0.14, size)
            cr.fill()
        else:
            cr.move_to(x + size * 0.28, y)
            cr.line_to(x + size * 0.28, y + size)
            cr.line_to(x + size * 0.85, y + size / 2)
            cr.close_path()
            cr.fill()
            cr.rectangle(x + size * 0.84, y, size * 0.14, size)
            cr.fill()
        cr.restore()

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        for action, bx, by, size in self._buttons:
            if bx <= x <= bx + size and by <= y <= by + size:
                if action == "nightlight":
                    subprocess.Popen([NIGHTLIGHT], start_new_session=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                else:
                    _playerctl(action)
                    self.refresh()
                return True
        return False
