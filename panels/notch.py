"""The notch.

macOS 26 turns the hardware notch into a panel: a black card hanging from
the top centre of the screen.  This one carries

* the media widget, with the album art and the playback controls,
* the calendar when nothing is playing,
* a row of round quick actions (clipboard, focus, screenshot),
* the clock and the battery on the right.
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
SCREENSHOT = os.path.expanduser("~/.config/river/screenshot.sh")


def _playerctl(command):
    subprocess.Popen(["playerctl", command], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


class Notch(Panel):
    NAMESPACE = "mac-notch"

    def __init__(self, metrics, shell):
        width = int(metrics.px("notch_width"))
        height = int(metrics.px("notch_height"))
        # the card slides up under the top edge when it is not wanted; the
        # surface stays on the screen, so the compositor keeps sending it
        # frames and the slide never freezes
        self._slide_distance = height
        super().__init__(
            metrics,
            layer="top",
            anchors={"top": True},
            keyboard=False,
            slide_edge="top",
        )
        self.shell = shell
        self._offset = self._slide_distance
        self.set_content_size(width, height)
        screen = metrics.width or 1366
        self.set_horizontal_offset(int((screen - width) / 2))
        self._media = None
        self._art = None
        self._art_url = None
        self._buttons: list = []
        self._battery = None
        self._charging = False

    def input_rects(self):
        """Only the card takes the pointer.

        When the card slides up out of the way the region is empty, so the
        menu bar underneath keeps its clicks.
        """
        return [(0, -self._offset, self.metrics.px("notch_width"),
                 self.metrics.px("notch_height"))]

    # -- visibility ----------------------------------------------------------

    def set_shown(self, shown):
        """Slide the notch in or out of the screen.

        The card hangs from the top edge, so hiding it means sliding it up
        and out of the way, exactly like macOS does when the pointer is
        not near the top of the display.
        """
        if shown:
            self.slide_to(0)
        else:
            self.slide_to(self._slide_distance)

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._media = state.now_playing()
        self._load_art()
        self._battery = state.battery_level()
        self._charging = state.battery_charging()
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
        scale = m.scale

        # the card slides up under the top edge when it is not wanted
        cr.save()
        cr.translate(0, -self._offset)

        # the card: a rounded rectangle hanging from the top edge, in the
        # colours of the theme so the text stays readable
        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, radius)
        cr.clip()
        dark = m.config.get("theme", "dark") == "dark"
        grad = cairo.LinearGradient(0, 0, 0, height)
        if dark:
            grad.add_color_stop_rgba(0.0, 0.03, 0.03, 0.04, 1.0)
            grad.add_color_stop_rgba(1.0, 0.06, 0.06, 0.08, 0.98)
        else:
            grad.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.97)
            grad.add_color_stop_rgba(1.0, 0.93, 0.93, 0.95, 0.95)
        cr.set_source(grad)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.restore()
        if not dark:
            draw.stroke_squircle(cr, 0, 0, width, height, radius,
                                 pal["separator"], 1.0, m.squareness)

        self._buttons = []
        pad = m.px("notch_pad")
        art = m.px("notch_art")

        # -- left: the media widget, or the calendar when nothing plays
        x = pad
        if not self._media:
            self._paint_calendar(cr, x, 10 * scale, 118 * scale,
                                 height - 20 * scale, pal)
        else:
            title, artist, status, position, length, _ = self._media
            if self._art is not None:
                pw, ph = self._art.get_width(), self._art.get_height()
                factor = art / max(pw, ph)
                cr.save()
                cr.translate(x, (height - art) / 2)
                cr.scale(factor, factor)
                Gdk.cairo_set_source_pixbuf(cr, self._art, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x, (height - art) / 2, art, art, 8,
                                   pal["fill_hover"], m.squareness)
                glyphs.speaker(cr, x + art * 0.26, (height - art * 0.44) / 2,
                               art * 0.48, pal["text_dim"])
            x += art + 12 * scale

            text_w = 128 * scale
            draw.draw_text(cr, x, height * 0.34, title, m.font("notch_font_size"),
                           pal["text"], weight="bold", baseline="middle",
                           max_width=text_w, ellipsize=True)
            if artist:
                draw.draw_text(cr, x, height * 0.58, artist,
                               m.font("notch_font_size") * 0.85,
                               pal["text_faint"], baseline="middle",
                               max_width=text_w, ellipsize=True)

            # the progress of the track
            if length:
                ratio = max(0.0, min(1.0, position / length))
                track_w = text_w
                track_y = height * 0.76
                draw.fill_squircle(cr, x, track_y, track_w, 3 * scale,
                                   1.5 * scale, pal["fill_hover"], 2.0)
                draw.fill_squircle(cr, x, track_y, track_w * ratio, 3 * scale,
                                   1.5 * scale, pal["text_dim"], 2.0)

            # playback controls
            bx = x + text_w + 16 * scale
            for action, shape in (("previous", "back"), ("play-pause", "play"),
                                  ("next", "forward")):
                self._paint_button(cr, bx, (height - 14 * scale) / 2,
                                   14 * scale, shape, pal)
                self._buttons.append((action, bx - 4 * scale,
                                      (height - 22 * scale) / 2, 22 * scale))
                bx += 24 * scale

        # -- middle: the quick actions ------------------------------------
        mid_x = width * 0.63
        button = 30 * scale
        actions = [
            ("clipboard", "clipboard", "Clipboard"),
            ("focus", "moon", "Focus"),
            ("screenshot", "camera", "Screenshot"),
            ("assistant", "sparkles", "Ask"),
        ]
        for index, (action, glyph, label) in enumerate(actions):
            cx = mid_x + (index - 1) * (button + 12 * scale)
            cy = height / 2 - 4 * scale
            cr.save()
            cr.set_source_rgba(*pal["fill_hover"])
            cr.arc(cx, cy, button / 2, 0, 2 * math.pi)
            cr.fill()
            cr.restore()
            size = 15 * scale
            self._draw_glyph(cr, glyph, cx - size / 2, cy - size / 2, size,
                             pal["text"])
            self._buttons.append((action, cx - button / 2, cy - button / 2,
                                  button))

        # -- right: the clock and the battery ----------------------------
        now = time.localtime()
        right = width - pad
        draw.draw_text(cr, right, height * 0.36, time.strftime("%H:%M", now),
                       m.font("notch_font_size") * 1.5, pal["text"],
                       align="right", baseline="middle")
        detail = time.strftime("%a %-d %b", now)
        if self._battery is not None:
            detail = f"{self._battery}%  " + detail
        draw.draw_text(cr, right, height * 0.64, detail,
                       m.font("notch_font_size") * 0.85, pal["text_faint"],
                       align="right", baseline="middle")

        # separators
        for sep_x in (width * 0.50, width * 0.755):
            cr.set_source_rgba(*pal["separator"])
            cr.rectangle(sep_x, height * 0.22, 1, height * 0.56)
            cr.fill()

        cr.restore()

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

    def _draw_glyph(self, cr, name, x, y, size, color):
        fn = getattr(glyphs, name, None)
        if fn is None:
            return
        fn(cr, x, y, size, color)

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        self.shell.keep_alive("notch")
        return False

    def on_click(self, x, y, button):
        for action, bx, by, size in self._buttons:
            if bx <= x <= bx + size and by <= y <= by + size:
                self._activate(action)
                return True
        return False

    def _activate(self, action):
        if action in ("previous", "play-pause", "next"):
            _playerctl(action)
            self.refresh()
        elif action == "clipboard":
            self.shell.open_clipboard()
        elif action == "focus":
            self.shell.open_focus_menu()
        elif action == "screenshot":
            subprocess.Popen([SCREENSHOT, "region"], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif action == "assistant":
            self.shell.assistant.open("ask")
