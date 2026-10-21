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
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ART_CACHE = "/tmp/macshell-art"


def _clock(seconds):
    """The time of a track, as minutes and seconds."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "0:00"
    if seconds < 0:
        seconds = 0
    return f"{seconds // 60}:{seconds % 60:02d}"
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
            # the overlay layer has no exclusive zone, so the card hangs
            # over the menu bar the way it does in macOS
            layer="overlay",
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
        self._clip = {}
        self._dnd = False
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
        self._clip = state.clipboard()
        self._dnd = state.dnd_on()
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
        media = self._media

        clip = self._clip or {}
        fresh = clip and (time.time() - clip.get("at", 0)) < 25
        if media:
            self._paint_media(cr, width, height, pad, scale, pal)
        elif fresh:
            self._paint_clipboard(cr, width, height, pad, scale, pal, clip)
        else:
            self._paint_calendar(cr, pad, 12 * scale, 132 * scale,
                                 height - 24 * scale, pal)

        # the quick actions on the right, the clock under them
        self._paint_actions(cr, width, height, pad, scale, pal)
        self._paint_clock(cr, width, height, pad, scale, pal)

        cr.restore()

    # -- the media card ------------------------------------------------------

    def _paint_media(self, cr, width, height, pad, scale, pal):
        """The card macOS shows when something is playing.

        The album art, the title, the progress of the track and the
        playback buttons, the way the notch of macOS 26 has it.
        """
        m = self.metrics
        title, artist, _status, position, length, _url = self._media
        art = 64 * scale

        # the album art
        art_x = pad
        art_y = 16 * scale
        draw.fill_squircle(cr, art_x, art_y, art, art, 10 * scale,
                           pal["fill_hover"], m.squareness)
        if self._art is not None:
            pw, ph = self._art.get_width(), self._art.get_height()
            factor = art / max(pw, ph)
            cr.save()
            cr.translate(art_x + (art - pw * factor) / 2,
                         art_y + (art - ph * factor) / 2)
            cr.scale(factor, factor)
            Gdk.cairo_set_source_pixbuf(cr, self._art, 0, 0)
            cr.paint()
            cr.restore()
        else:
            draw.draw_text(cr, art_x + art / 2, art_y + art / 2,
                           (title or "?")[0].upper(), art * 0.42,
                           pal["text_dim"], weight="bold", align="center",
                           baseline="middle")

        # the title and the artist
        text_x = art_x + art + 16 * scale
        draw.draw_text(cr, text_x, 34 * scale, title or "",
                       m.font("notch_font_size") * 1.15, pal["text"],
                       weight="bold", baseline="middle",
                       max_width=220 * scale, ellipsize=True)
        if artist:
            draw.draw_text(cr, text_x, 56 * scale, artist,
                           m.font("notch_font_size") * 0.95, pal["text_dim"],
                           baseline="middle", max_width=220 * scale,
                           ellipsize=True)

        # the airplay button
        glyphs.airplay(cr, width - 250 * scale, 30 * scale, 16 * scale,
                       pal["text_dim"])

        # the progress of the track, with the time on both sides
        bar_x = 56 * scale
        bar_w = width - 250 * scale - bar_x
        bar_y = 92 * scale
        draw.draw_text(cr, pad, bar_y, _clock(position), 10 * scale,
                       pal["text_faint"], baseline="middle")
        draw.fill_squircle(cr, bar_x, bar_y - 1.5 * scale, bar_w, 3 * scale,
                           1.5 * scale, pal["fill_hover"], 2.0)
        if length:
            ratio = max(0.0, min(1.0, position / length))
            draw.fill_squircle(cr, bar_x, bar_y - 1.5 * scale,
                               bar_w * ratio, 3 * scale, 1.5 * scale,
                               pal["text_dim"], 2.0)
        draw.draw_text(cr, bar_x + bar_w + 10 * scale, bar_y, _clock(length),
                       10 * scale, pal["text_faint"], baseline="middle")

        # the playback buttons, the way macOS lines them up
        row_y = 118 * scale
        centre = 198 * scale
        playing = (self._media[2] or "").lower() == "playing"
        buttons = [
            ("shuffle", "shuffle", 16 * scale),
            ("previous", "back", 18 * scale),
            ("play-pause", "pause" if playing else "play", 24 * scale),
            ("next", "forward", 18 * scale),
            ("like", "star", 16 * scale),
        ]
        gap = 26 * scale
        x = centre - (len(buttons) - 1) * gap / 2
        for action, shape, size in buttons:
            if action == "like":
                glyphs.star(cr, x - size / 2, row_y - size / 2, size,
                            pal["text_dim"])
            else:
                self._paint_button(cr, x - size / 2, row_y - size / 2, size,
                                   shape, pal)
            self._buttons.append((action, x - 12 * scale, row_y - 12 * scale,
                                  24 * scale))
            x += gap

    def _paint_clipboard(self, cr, width, height, pad, scale, pal, clip):
        """What was just copied, the way macOS shows it in the notch."""
        m = self.metrics
        text = clip.get("text") or ""
        image = clip.get("image")

        if image:
            art = 64 * scale
            draw.fill_squircle(cr, pad, 16 * scale, art, art, 10 * scale,
                               pal["fill_hover"], m.squareness)
            pixbuf = self._image_for(image)
            if pixbuf is not None:
                iw, ih = pixbuf.get_width(), pixbuf.get_height()
                factor = min(art / iw, art / ih)
                cr.save()
                cr.translate(pad + (art - iw * factor) / 2,
                             16 * scale + (art - ih * factor) / 2)
                cr.scale(factor, factor)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            draw.draw_text(cr, pad + art + 16 * scale, 40 * scale, "Copied",
                           m.font("notch_font_size"), pal["text_faint"],
                           baseline="middle")
            draw.draw_text(cr, pad + art + 16 * scale, 62 * scale, "an image",
                           m.font("notch_font_size") * 1.1, pal["text"],
                           weight="bold", baseline="middle")
            return

        draw.draw_text(cr, pad, 34 * scale, "Copied", 11 * scale,
                       pal["text_faint"], baseline="middle")
        for index, line in enumerate(text.splitlines()[:3]):
            draw.draw_text(cr, pad, 58 * scale + index * 20 * scale, line,
                           m.font("notch_font_size") * 1.05, pal["text"],
                           weight="bold" if index == 0 else "normal",
                           baseline="middle", max_width=300 * scale,
                           ellipsize=True)

    def _image_for(self, path):
        """The picture that was copied."""
        if getattr(self, "_clip_image", None) is not None:
            return self._clip_image
        pixbuf = None
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:  # noqa: BLE001
            pixbuf = None
        self._clip_image = pixbuf
        return pixbuf

    # -- the quick actions and the clock --------------------------------------

    def _paint_actions(self, cr, width, height, pad, scale, pal):
        """The round buttons on the right of the card."""
        m = self.metrics
        actions = [
            ("clipboard", "clipboard", "Clipboard"),
            ("focus", "moon", "Focus"),
            ("screenshot", "camera", "Screenshot"),
            ("assistant", "sparkles", "Ask"),
        ]
        size = 30 * scale
        gap = 10 * scale
        x = width - pad - size * 2 - gap
        y = 16 * scale
        lit = []
        if self._clip and (time.time() - self._clip.get("at", 0)) < 25:
            lit.append("clipboard")
        if self._dnd:
            lit.append("focus")
        for index, (action, glyph, label) in enumerate(actions):
            col = index % 2
            row = index // 2
            cx = x + col * (size + gap)
            cy = y + row * (size + gap)
            cr.save()
            if action in lit:
                cr.set_source_rgba(*pal["accent"])
            else:
                cr.set_source_rgba(*pal["fill_hover"])
            cr.arc(cx + size / 2, cy + size / 2, size / 2, 0, 2 * math.pi)
            cr.fill()
            cr.restore()
            icon = 15 * scale
            self._draw_glyph(cr, glyph, cx + (size - icon) / 2,
                             cy + (size - icon) / 2, icon,
                             pal["on_accent"] if action in lit else pal["text"])
            self._buttons.append((action, cx, cy, size))

    def _paint_clock(self, cr, width, height, pad, scale, pal):
        """The clock and the battery, under the quick actions."""
        m = self.metrics
        now = time.localtime()
        right = width - pad
        y = height - 38 * scale
        draw.draw_text(cr, right, y, time.strftime("%H:%M", now),
                       m.font("notch_font_size") * 1.35, pal["text"],
                       align="right", baseline="middle")
        detail = time.strftime("%a %-d %b", now)
        if self._battery is not None:
            detail = f"{self._battery}%  " + detail
        draw.draw_text(cr, right, y + 20 * scale, detail,
                       m.font("notch_font_size") * 0.85, pal["text_faint"],
                       align="right", baseline="middle")

    def _paint_calendar(self, cr, x, y, w, h, pal):
        """The little calendar the notch shows when nothing is playing."""
        import datetime

        m = self.metrics
        scale = m.scale
        today = datetime.date.today()
        cy = y + h / 2

        draw.draw_text(cr, x, cy - 34 * scale, today.strftime("%a").upper(),
                       11 * scale, pal["text_faint"], weight="bold",
                       baseline="middle")
        draw.draw_text(cr, x, cy, str(today.day), 40 * scale, pal["text"],
                       weight="bold", baseline="middle")
        draw.draw_text(cr, x, cy + 32 * scale, today.strftime("%B %Y"),
                       11 * scale, pal["text_faint"], baseline="middle")

    def _paint_button(self, cr, x, y, size, shape, pal):
        color = pal["text_dim"]
        cr.save()
        cr.set_source_rgba(*color)
        if shape == "pause":
            cr.rectangle(x + size * 0.24, y, size * 0.16, size)
            cr.fill()
            cr.rectangle(x + size * 0.58, y, size * 0.16, size)
            cr.fill()
        elif shape == "play":
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
        if action in ("previous", "play-pause", "next", "shuffle", "love"):
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
        elif action == "shuffle":
            _playerctl("shuffle")
            self.refresh()
        elif action == "like":
            _playerctl("love")
            self.refresh()
