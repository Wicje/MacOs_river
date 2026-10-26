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
import json
import os
import subprocess
import threading
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from ..macui import draw, glyphs, localsend, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ART_CACHE = "/tmp/macshell-art"


ACTIONS = [
    ("clipboard", "clipboard", "Clipboard"),
    ("focus", "moon", "Focus"),
    ("timer", "timer", "Focus timer"),
    ("screenshot", "camera", "Screenshot"),
    ("assistant", "sparkles", "Ask"),
    ("dictation", "microphone", "Dictation"),
    ("phonehub", "phone", "Phone Hub"),
]


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
        # the card slides with a spring: it overshoots the stop and
        # settles, the way the Dynamic Island breathes in macOS
        self.spring_slide = True
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
        self._activities = []
        self._flash = []
        self._activity = None
        self._eq_source = None
        self._timer_source = None
        self._timer = {"total": 1500.0, "left": 1500.0, "running": False,
                       "till": 0.0}
        # the shelf: uri-lists dropped on the card park here, and stay
        # across restarts, the way a pocket keeps its keys
        self._shelf = []
        self._shelf_art = {}
        self._shelf_shown = False
        self._shelf_hover = False
        self._shelf_max = 24
        self._shelf_pointer = (-1.0, -1.0)
        self._load_shelf()
        self._shelf_wire_dnd()

    def input_rects(self):
        """Only the card takes the pointer.

        When the card slides up out of the way the region is empty, so the
        menu bar underneath keeps its clicks.
        """
        width = self.metrics.px("notch_width")
        height = self.content_size()[1] or self.metrics.px("notch_height")
        return [(0, -self._offset, width, height)]

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
        # the lights of the notch: macOS shows an orange dot while a
        # program records, a green one while a camera streams
        self._mic = state.mic_active()
        self._camera = state.camera_active()
        # the island: whatever is happening, strongest activity first
        self._activities = state.activities()
        self._flash = [row for row in self._activities
                       if row["priority"] == "background"]
        self._activity = next((row for row in self._activities
                               if row["priority"] in ("critical", "high",
                                                      "normal", "low")),
                              None)
        self._ensure_eq_loop()
        self._ensure_timer_loop()
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

        # the card: a rounded rectangle hanging from the top edge.  macOS
        # paints the notch in ink that swallows the bar behind it, so the
        # card reads as a hole in the picture, not as a window.
        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, radius)
        cr.clip()
        dark = m.config.get("theme", "dark") == "dark"
        # the bloom of the card into the bar behind it, painted first so
        # the card lands on top of its own shadow
        cr.restore()
        cr.save()
        for band, alpha in ((3.5, 0.16), (7.0, 0.08), (11.0, 0.035)):
            cr.new_sub_path()
            draw.rounded_path(cr, band, band, width - band * 2,
                              height - band * 2 + 6 * scale, radius)
            cr.set_source_rgba(0.0, 0.0, 0.0, alpha if dark else alpha * 0.6)
            cr.set_line_width(band)
            cr.stroke()
        cr.restore()
        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, radius)
        cr.clip()
        grad = cairo.LinearGradient(0, 0, 0, height)
        if dark:
            grad.add_color_stop_rgba(0.0, 0.023, 0.023, 0.028, 1.0)
            grad.add_color_stop_rgba(1.0, 0.055, 0.055, 0.07, 0.99)
        else:
            grad.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.97)
            grad.add_color_stop_rgba(1.0, 0.93, 0.93, 0.95, 0.95)
        cr.set_source(grad)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        # the underside of the card catches the light, the way the glass
        # of Tahoe carries a bright bottom edge
        under = cairo.LinearGradient(0, height - 8 * scale, 0, height)
        under.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.0)
        under.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0,
                                  0.05 if dark else 0.0)
        cr.set_source(under)
        cr.rectangle(0, height - 8 * scale, width, 8 * scale)
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
        if self._activity is not None:
            self._paint_activity(cr, width, height, pad, scale, pal,
                                 self._activity)
        elif self._flash:
            # a finished thing pays a short visit: the accent side of the
            # card, so it is seen without shouting
            self._paint_flash(cr, width, height, pad, scale, pal,
                              self._flash[0])
        elif media:
            self._paint_media(cr, width, height, pad, scale, pal)
        elif fresh:
            self._paint_clipboard(cr, width, height, pad, scale, pal, clip)
        elif self._timer["running"]:
            self._paint_timer(cr, width, height, pad, scale, pal)
        elif self._shelf and self._shelf_shown:
            self._paint_shelf(cr, width, height, pad, scale, pal)
        else:
            self._paint_calendar(cr, pad, 12 * scale, 132 * scale,
                                 height - 24 * scale, pal)

        # the quick actions on the right, the clock under them
        self._paint_actions(cr, width, height, pad, scale, pal)
        self._paint_clock(cr, width, height, pad, scale, pal)

        # the page dots of the left card: the calendar and the shelf
        if (self._activity is None and not media and not fresh
                and not self._timer["running"]):
            self._paint_page_dots(cr, pad, width, height, scale, pal)

        # the divider between the left card and the numbers on the right
        if ((self._activity is None and not media
             and not self._timer["running"])):
            line_x = pad + 144 * scale
            cr.set_source_rgba(*pal["separator"])
            cr.set_line_width(1.0)
            cr.move_to(line_x, 14 * scale)
            cr.line_to(line_x, height - 14 * scale)
            cr.stroke()

        cr.restore()

    # -- the island activity card ---------------------------------------------

    _ACTIVITY_GLYPHS = {
        "download": "shield",  # keeper until a download glyph exists
        "recover": "moon",
    }

    def _paint_activity(self, cr, width, height, pad, scale, pal, row):
        """The island card: what is happening, with progress if it has any."""
        m = self.metrics
        title = (row.get("title") or "").strip()
        detail = row.get("detail") or ""
        progress = row.get("progress")
        if not isinstance(progress, (int, float)) or not 0.0 <= progress <= 1.0:
            progress = None
        kind = (row.get("kind") or "generic").lower()
        glyph = self._ACTIVITY_GLYPHS.get(kind, "sparkles")

        box = 38 * scale
        strong = row["priority"] in ("critical", "high")
        if strong:
            color = (*pal["accent"], 0.18)
        else:
            color = pal["fill_hover"]
        draw.fill_squircle(cr, pad, 18 * scale, box, box, 10 * scale, color)
        glyph = self._ACTIVITY_GLYPHS.get(kind)
        if glyph and hasattr(glyphs, glyph):
            self._draw_glyph(cr, glyph, pad + (box - 20 * scale) / 2,
                             18 * scale + (box - 20 * scale) / 2, 20 * scale,
                             pal["text"] if strong else pal["text_dim"])
        else:
            draw.draw_text(cr, pad + box / 2, 18 * scale + box / 2,
                           (title[0].upper() if title else (kind[0].upper()
                            if kind else "?")),
                           16 * scale, pal["text"], weight="bold",
                           align="center", baseline="middle")

        text_x = pad + box + 14 * scale
        draw.draw_text(cr, text_x, 32 * scale, title or "…",
                       m.font("notch_font_size") * 1.15, pal["text"],
                       weight="bold", baseline="middle",
                       max_width=200 * scale, ellipsize=True)
        if detail:
            draw.draw_text(cr, text_x, 54 * scale, detail,
                           m.font("notch_font_size") * 0.92, pal["text_dim"],
                           baseline="middle", max_width=200 * scale,
                           ellipsize=True)
        if progress is None:
            draw.draw_text(cr, width - 150 * scale, 40 * scale,
                           row["priority"].upper(), 10 * scale,
                           pal["text_faint"], align="right",
                           baseline="middle")
            return

        right = width - 150 * scale
        draw.draw_text(cr, right, 40 * scale, f"{int(progress * 100)}%",
                       15 * scale, pal["text"], weight="bold",
                       align="right", baseline="middle")
        bar_x = 96 * scale
        bar_y = 108 * scale
        bar_w = right - 14 * scale - bar_x
        draw.fill_squircle(cr, bar_x, bar_y - 1.5 * scale, bar_w, 3 * scale,
                           1.5 * scale, pal["fill_hover"], 2.0)
        draw.fill_squircle(cr, bar_x, bar_y - 1.5 * scale, bar_w * progress,
                           3 * scale, 1.5 * scale, pal["text"], 2.0)
        self._buttons.append(("activity", pad, 18 * scale,
                              int(width - 150 * scale - pad)))

    def _paint_flash(self, cr, width, height, pad, scale, pal, row):
        """A completed activity, paying a short accent visit."""
        m = self.metrics
        draw.draw_text(cr, pad, 26 * scale, "done", 10 * scale,
                       pal["accent"], weight="bold", baseline="middle")
        draw.draw_text(cr, pad, 48 * scale, row.get("title") or "",
                       m.font("notch_font_size") * 1.05, pal["text"],
                       weight="bold", baseline="middle",
                       max_width=240 * scale, ellipsize=True)

    # -- the media card ------------------------------------------------------

    def _paint_eq(self, cr, x, y, scale, pal, playing):
        """Five equalizer bars, breathing while the song plays.

        The bars stand on a rounded line like the ones macOS puts in the
        volume HUD; when the song rests they hold one still shape.
        """
        gap = 5.5 * scale
        if playing:
            now = time.monotonic()
            for index in range(5):
                wave = (math.sin(now * 4.6 + index * 0.9) * 0.5
                        + math.sin(now * 2.7 + index * 1.7) * 0.5)
                h = (4.5 + 9.5 * (0.5 + 0.5 * wave)) * scale
                draw.fill_squircle(cr, x + index * gap, y - h / 2,
                                   3.0 * scale, h, 1.5 * scale,
                                   (*pal["text"][:3], 0.9))
        else:
            for index, part in enumerate((0.35, 0.55, 0.95, 0.55, 0.35)):
                h = 10.0 * scale * part
                draw.fill_squircle(cr, x + index * gap, y - h / 2,
                                   3.0 * scale, h, 1.5 * scale,
                                   (*pal["text"][:3], 0.45))

    def _eq_tick(self):
        """Breathes the equalizer until the song stops being played."""
        playing = bool(self._media) and \
            (self._media[2] or "").lower() == "playing"
        if not playing:
            self._eq_source = None
            return False
        self.area.queue_draw()
        return True

    def _ensure_eq_loop(self):
        source = getattr(self, "_eq_source", None)
        playing = bool(self._media) and \
            (self._media[2] or "").lower() == "playing"
        if playing and source is None:
            self._eq_source = GLib.timeout_add(90, self._eq_tick)
        elif not playing and source is not None:
            GLib.source_remove(source)
            self._eq_source = None
            self.area.queue_draw()

    # -- the focus timer --------------------------------------------------------

    def _timer_remaining(self):
        timer = self._timer
        if timer["running"]:
            return max(0.0, timer["till"] - time.time())
        return max(0.0, timer["left"])

    def _timer_tick(self):
        """Breathes the countdown while the focus runs."""
        if not self._timer["running"]:
            self._timer_source = None
            return False
        remaining = self._timer_remaining()
        if remaining <= 0.0:
            self._timer["running"] = False
            self._timer["left"] = self._timer["total"]
            self._timer_source = None
            self.redraw()
            try:
                self.shell.show_message("Focus timer", "The focus is done. "
                                        "Stand up and drink some water.")
                from ..macui import sound
                sound.play("unlock")
            except Exception:
                pass
            return False
        self.area.queue_draw()
        return True

    def _ensure_timer_loop(self):
        source = self._timer_source
        if self._timer["running"]:
            if source is None:
                self._timer_source = GLib.timeout_add(500, self._timer_tick)
        elif source is not None:
            GLib.source_remove(source)
            self._timer_source = None
            self.area.queue_draw()

    def _toggle_timer(self):
        """Click: start; click again: pause; a parked pause can reset."""
        timer = self._timer
        if timer["running"]:
            timer["left"] = self._timer_remaining()
            timer["running"] = False
        elif timer["left"] < timer["total"]:
            # a parked countdown goes back to the start cleanly
            timer["left"] = timer["total"]
        else:
            timer["till"] = time.time() + timer["left"]
            timer["running"] = True
        self.refresh()

    # -- the file shelf ---------------------------------------------------------

    SHELF_FILE = os.path.expanduser("~/.local/state/macshell/shelf.json")

    def _load_shelf(self):
        try:
            with open(self.SHELF_FILE) as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(saved, list):
            self._shelf = [entry for entry in saved
                           if isinstance(entry, str)
                           and os.path.exists(entry)][: self._shelf_max]

    def _save_shelf(self):
        try:
            os.makedirs(os.path.dirname(self.SHELF_FILE), exist_ok=True)
            with open(self.SHELF_FILE, "w") as fh:
                json.dump([entry["path"] for entry in self._shelf], fh)
        except OSError:
            pass

    def _shelf_wire_dnd(self):
        """The card accepts uri-lists, like a tray that catches files."""
        targets = [Gtk.TargetEntry.new("text/uri-list", 0, 0),
                   Gtk.TargetEntry.new("text/plain", 0, 1)]
        self.area.drag_dest_set(Gtk.DestDefaults.ALL, targets,
                                Gdk.DragAction.COPY)
        self.area.connect("drag-data-received", self._shelf_received)
        self.area.connect("drag-motion", self._shelf_motion)
        self.area.connect("drag-leave", self._shelf_leave)
        self.area.connect("drag-drop", self._shelf_drop)

    def _shelf_motion(self, _area, _context, _x, y, _time):
        self._shelf_hover = True
        self.area.queue_draw()
        return False

    def _shelf_leave(self, _area, _context, _time):
        self._shelf_hover = False
        self.area.queue_draw()

    def _shelf_drop(self, _area, context, _x, _y, _time):
        context.drop_finish(True, _time)
        return True

    def _shelf_received(self, _area, _context, _x, _y, data, _info, _time):
        self._shelf_hover = False
        uris = data.get_uris() if data is not None else []
        added = 0
        for uri in uris:
            path = GLib.filename_from_uri(uri)[0] \
                if uri.startswith("file") else uri
            if not path or not os.path.exists(path):
                continue
            self._shelf = [entry for entry in self._shelf
                           if entry != path]
            self._shelf.insert(0, path)
            added += 1
        self._shelf = self._shelf[: self._shelf_max]
        if added:
            self._shelf_shown = True
            self._save_shelf()
        self.redraw()

    def _shelf_thumbs(self):
        """Drop the stale paths and refresh the small previews."""
        self._shelf = [entry for entry in self._shelf
                       if os.path.exists(entry)]
        art = 40 * (self.metrics.scale or 1)
        for path in self._shelf:
            if path in self._shelf_art:
                continue
            pixbuf = None
            if os.path.splitext(path)[1].lower() in (".png", ".jpg", ".jpeg",
                                                     ".webp", ".gif", ".bmp"):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        path, art, art)
                except Exception:
                    pixbuf = None
            self._shelf_art[path] = pixbuf

    def _paint_shelf(self, cr, width, height, pad, scale, pal):
        """The shelf page: a dashed tray with the files that were dropped."""
        m = self.metrics
        self._shelf_thumbs()
        x, y, w, h = pad, 12 * scale, 132 * scale, height - 24 * scale
        hot = self._shelf_hover

        line_r = 12 * scale
        cr.save()
        cr.set_line_width(1.4 * scale)
        cr.set_source_rgba(*pal["text_faint"][:3],
                           0.85 if hot else 0.45)
        cr.set_dash([3 * scale, 3.2 * scale])
        draw.rounded_path(cr, x, y, w, h, line_r)
        cr.stroke()
        cr.restore()

        # the cards of the shelf: newest first, two per row
        cell = 44 * scale
        gap = 8 * scale
        cols = 2
        shown = self._shelf[: cols * 2]
        row = height if False else None
        # the pointer, the same room the card buttons measure in
        px, py = self._shelf_pointer
        hovered = -1
        for index, _path in enumerate(shown):
            col = index % cols
            hx = x + 10 * scale + col * (cell + gap)
            hy = y + 8 * scale + (index // cols) * (cell + gap)
            if hx - 2 * scale <= px <= hx + cell + 2 * scale and \
                    hy - 2 * scale <= py <= hy + cell + 2 * scale:
                hovered = index
                break
        for index, path in enumerate(shown):
            col = index % cols
            gx = x + 10 * scale + col * (cell + gap)
            gy = y + 8 * scale + (index // cols) * (cell + gap)
            if index == hovered:
                chip = 13 * scale
                cx, cy = gx + cell - chip, gy - 2 * scale
                draw.fill_squircle(cr, cx, cy, chip, chip, 5 * scale,
                                   (1.0, 0.34, 0.32, 1.0), m.squareness)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
                cr.set_line_width(1.1 * scale)
                off = chip * 0.30
                cr.move_to(cx + off, cy + off)
                cr.line_to(cx + chip - off, cy + chip - off)
                cr.stroke()
                cr.move_to(cx + chip - off, cy + off)
                cr.line_to(cx + off, cy + chip - off)
                cr.stroke()
                # the chip wins the hit test: it is offered before the card
                self._buttons.insert(
                    0, ("shelf:del:%d" % index, cx - 3 * scale,
                        cy - 3 * scale, chip + 6 * scale))
            gy = y + 8 * scale + (index // cols) * (cell + gap)
            draw.fill_squircle(cr, gx, gy, cell, cell, 8 * scale,
                               pal["fill_hover"], m.squareness)
            pixbuf = self._shelf_art.get(path)
            if pixbuf is not None:
                pw, ph = pixbuf.get_width(), pixbuf.get_height()
                factor = (cell - 8 * scale) / max(pw, ph)
                cr.save()
                cr.translate(gx + cell / 2 - pw * factor / 2,
                             gy + cell / 2 - ph * factor / 2)
                cr.scale(factor, factor)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            else:
                name = os.path.basename(path)
                letter = (name[:1] or "?").upper()
                ext = os.path.splitext(path)[1].lower().lstrip(".")[:4]
                draw.draw_text(cr, gx + cell / 2, gy + cell * 0.40, letter,
                               cell * 0.34, pal["text_dim"], weight="bold",
                               align="center", baseline="middle")
                if ext:
                    draw.draw_text(cr, gx + cell / 2, gy + cell * 0.72, ext,
                                   8.5 * scale, pal["text_faint"],
                                   align="center", baseline="middle")
            self._buttons.append(("shelf:open:%d|%s" % (index, path),
                                  gx, gy, cell))
        if self._shelf:
            extra = len(self._shelf) - len(shown)
            if extra > 0:
                draw.draw_text(cr, x + w / 2, y + h - 12 * scale,
                               f"+{extra} more", 9 * scale,
                               pal["text_faint"], align="center",
                               baseline="middle")
            else:
                draw.draw_text(cr, x + w / 2, y + h - 12 * scale,
                               "Click opens · right-click sends", 8.0 * scale,
                               pal["text_faint"], align="center",
                               baseline="middle")
        else:
            draw.draw_text(cr, x + w / 2, y + h / 2, "Drop files here",
                           11 * scale, pal["text_dim"], align="center",
                           weight="bold", baseline="middle")
            draw.draw_text(cr, x + w / 2, y + h / 2 + 16 * scale,
                           "They stay in the notch.", 9.5 * scale,
                           pal["text_faint"], align="center",
                           baseline="middle")

    def _paint_page_dots(self, cr, pad, width, height, scale, pal):
        """Two dots under the left card: the calendar and the shelf."""
        if not self._shelf:
            return
        gap = 5 * scale
        total = 3.6 * scale * 2 + gap
        x = pad + 30 * scale - total / 2
        y = height - 10 * scale
        for index, name in enumerate(("calendar", "shelf")):
            active = (name == "shelf") == self._shelf_shown
            piece = 15 * scale if active else 3.6 * scale
            draw.fill_squircle(cr, x, y - 1.8 * scale, piece, 3.6 * scale,
                               1.8 * scale,
                               pal["text"] if active
                               else (*pal["text_faint"][:3], 0.5))
            self._buttons.append(("page:" + name, x - 2 * scale, y - 5 * scale,
                                  piece + 4 * scale))
            x += piece + gap

    def _remove_shelf(self, index):
        if 0 <= index < len(self._shelf):
            self._shelf.pop(index)
            self._save_shelf()
            if not self._shelf:
                self._shelf_shown = False
            self.redraw()

    def _send_shelf(self, index):
        """AirDrop in disguise: the card goes to a LocalSend receiver.

        The discovery and the send take seconds, so they run on a
        worker thread and only the notification comes back to the UI.
        """
        if not (0 <= index < len(self._shelf)):
            return
        path = self._shelf[index]
        if not os.path.exists(path):
            self._remove_shelf(index)
            return
        self.shell.show_message("Send", "Looking for nearby devices…")
        threading.Thread(target=self._send_runner, args=(path,),
                         daemon=True).start()

    def _send_runner(self, path):
        device, ok, reason = localsend.send(path)
        def tell():
            if ok:
                self.shell.show_message("Send",
                                        "Sent to %s." % device["alias"])
            else:
                self.shell.show_message("Send", reason)
        GLib.idle_add(tell)

    def _paint_timer(self, cr, width, height, pad, scale, pal):
        """The focus page: a red ring over the time that is left.

        Drawn where the calendar sits, so the page swap is one swap of
        content and not a move of the whole card.
        """
        m = self.metrics
        timer = self._timer
        total = max(1.0, timer["total"])
        fraction = min(1.0, (self._timer_remaining() + 0.4) / total)
        left = self._timer_remaining()

        cx = pad + 30 * scale
        cy = 12 * scale + (height - 24 * scale) / 2
        r = 22 * scale
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        # the glow of the ring, the way Nusa lets its timer breathe red
        cr.set_source_rgba(1.0, 0.30, 0.28, 0.10)
        cr.arc(cx, cy, r + 8 * scale, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(*pal["fill_hover"])
        cr.set_line_width(4.5 * scale)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(1.0, 0.34, 0.32, 1.0)
        cr.arc(cx, cy, r, -math.pi / 2,
               -math.pi / 2 + 2 * math.pi * max(0.01, fraction))
        cr.stroke()
        # the time inside the ring, tabular so it does not tremble
        minutes, seconds = divmod(int(round(left)), 60)
        draw.draw_text(cr, cx, cy, f"{minutes}:{seconds:02d}",
                       m.font("notch_font_size") * 1.05, pal["text"],
                       weight="bold", align="center", baseline="middle")

        x = cx + r + 18 * scale
        draw.draw_text(cr, x, cy - 22 * scale, "Focus", 11 * scale,
                       pal["text_dim"], weight="bold", baseline="middle")
        draw.draw_text(cr, x, cy + 2 * scale,
                       "The time counts down in red.",
                       10.5 * scale, pal["text_faint"], baseline="middle",
                       max_width=150 * scale)
        draw.draw_text(cr, x, cy + 22 * scale,
                       "The chip pauses it; a pause resets it.",
                       10.5 * scale, pal["text_faint"], baseline="middle",
                       max_width=150 * scale)

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

        # the title and the artist, with the bars of the song breathing
        # on the right, the way the closed notch of Nusa carries its wave
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
        playing = (_status or "").lower() == "playing"
        self._paint_eq(cr, width - 290 * scale, 34 * scale, scale, pal,
                       playing)

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
        """The round buttons of the card: one calm row, centred.

        The row sits in the space between the top edge and the clock, so
        however many buttons the user keeps, they never land on the
        numbers.  Only when the card is too narrow does the row wrap into
        a second one.
        """
        wanted = self.metrics.config.get("notch_actions")
        actions = [entry for entry in ACTIONS if not wanted
                   or entry[0] in wanted]
        size = 24 * scale
        gap = 7 * scale
        usable = width - pad * 2
        per_row = max(2, int((usable + gap) / (size + gap)))
        rows = max(1, -(-len(actions) // per_row))

        # where the row may live: under the top edge, over the clock
        top_zone = 10 * scale
        clock_top = height - 50 * scale
        space = max(0.0, clock_top - top_zone)
        grid_h = rows * size + (rows - 1) * gap
        y = top_zone + max(0.0, space - grid_h) / 2
        row_w = (per_row * size + (per_row - 1) * gap)
        x0 = (width - min(row_w, usable)) / 2

        pointer = getattr(self, "pointer", (-1, -1))
        lit = set()
        clip = self._clip or {}
        if clip and (time.time() - clip.get("at", 0)) < 25:
            lit.add("clipboard")
        if self._dnd:
            lit.add("focus")
        if state.dictation_active():
            lit.add("dictation")
        if state.phonehub_running():
            lit.add("phonehub")
        total = max(1.0, self._timer["total"])
        left = self._timer_remaining()
        timer_running = self._timer["running"]
        timer_fraction = min(1.0, left / total)

        for index, (action, glyph, label) in enumerate(actions):
            col = index % per_row
            row = index // per_row
            cx = x0 + col * (size + gap)
            cy = y + row * (size + gap)
            hovered = (pointer[0] is not None
                       and cx <= pointer[0] <= cx + size
                       and cy <= pointer[1] <= cy + size)
            on = action in lit
            center = (cx + size / 2, cy + size / 2)
            if glyph == "timer":
                # the focus timer speaks in red, not in the accent
                on = timer_running
            if on:
                # the halo of a running feature, one ring behind the chip
                color = (1.0, 0.34, 0.32) if glyph == "timer" \
                    else pal["accent"][:3]
                cr.set_source_rgba(*color, 0.30)
                cr.arc(center[0], center[1], size / 2 + 3 * scale,
                       0, 2 * math.pi)
                cr.set_line_width(2.0 * scale)
                cr.stroke()
            fill = None
            if on and glyph == "timer":
                fill = (1.0, 0.34, 0.32, 1.0)
            elif on:
                fill = pal["accent"]
            elif hovered:
                fill = pal["text_dim"]
            else:
                fill = pal["fill_hover"]
            cr.set_source_rgba(*fill)
            cr.arc(center[0], center[1], size / 2, 0, 2 * math.pi)
            cr.fill()
            icon = 13 * scale
            if glyph == "timer":
                icon_color = ((1.0, 1.0, 1.0, 1.0) if timer_running
                              else (pal["text"] if hovered else pal["text"]))
                glyphs.timer(cr, cx + (size - icon) / 2,
                             cy + (size - icon) / 2, icon, icon_color,
                             fraction=(0.99 if timer_running
                                       else timer_fraction),
                             active=timer_running)
            else:
                self._draw_glyph(cr, glyph, cx + (size - icon) / 2,
                                 cy + (size - icon) / 2, icon,
                                 pal["on_accent"] if on else
                                 (pal["text"] if hovered else pal["text"]))
            self._buttons.append((action, cx, cy, size))

    def _paint_clock(self, cr, width, height, pad, scale, pal):
        """The clock and the battery, under the quick actions."""
        m = self.metrics
        now = time.localtime()
        right = width - pad
        y = height - 38 * scale
        time_text = time.strftime("%H:%M", now)
        time_w = draw.text_width(cr, time_text,
                                 m.font("notch_font_size") * 1.35)
        detail = time.strftime("%a %-d %b", now)
        if self._battery is not None:
            detail = f"{self._battery}%  " + detail
        draw.draw_text(cr, right, y, time_text,
                       m.font("notch_font_size") * 1.35, pal["text"],
                       align="right", baseline="middle")
        draw.draw_text(cr, right, y + 20 * scale, detail,
                       m.font("notch_font_size") * 0.85, pal["text_faint"],
                       align="right", baseline="middle")
        # the lights: blue while the camera streams, the familiar orange
        # while the microphone records.  They stand before the clock, so
        # they read as indicators of the machine, not of the time.
        lights = []
        if getattr(self, "_camera", False):
            lights.append((0.21, 0.47, 0.91))
        if getattr(self, "_mic", False):
            lights.append((1.00, 0.58, 0.00))
        if lights:
            dot = 8 * scale
            dot_x = right - time_w - 24 * scale
            for color in lights:
                draw.fill_squircle(cr, dot_x, y - dot / 2, dot, dot,
                                   dot / 2, color, 2.0)
                dot_x -= dot + 6 * scale

    def _paint_calendar(self, cr, x, y, w, h, pal):
        """The little calendar the notch shows when nothing is playing."""
        import datetime

        m = self.metrics
        scale = m.scale
        today = datetime.date.today()
        cy = y + h / 2

        # the weekday in the red of the macOS calendar, the day bold
        draw.draw_text(cr, x, cy - 34 * scale, today.strftime("%a").upper(),
                       11 * scale, (0.98, 0.23, 0.19, 1.0), weight="bold",
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
        moved = self._shelf_pointer != (x, y)
        self._shelf_pointer = (x, y)
        # the remove chip of the shelf card follows the pointer, so the
        # page needs a small repaint while the pointer walks a card
        if moved and self._shelf_shown and self._shelf:
            self.redraw()
        return False

    def _open_shelf_item(self, action):
        # the shelf button carries its rank and its path
        _num, path = action.split(":open:", 1)[1].split("|", 1)
        if os.path.exists(path):
            subprocess.Popen(["xdg-open", path], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            self._shelf = [entry for entry in self._shelf if entry != path]
            self._save_shelf()
            self.redraw()

    def on_click(self, x, y, button):
        for action, bx, by, size in self._buttons:
            if bx <= x <= bx + size and by <= y <= by + size:
                if action == "page:calendar":
                    self._shelf_shown = False
                    self.redraw()
                elif action == "page:shelf":
                    self._shelf_shown = True
                    self.redraw()
                elif action.startswith("shelf:del:"):
                    self._remove_shelf(int(action.rsplit(":", 1)[1]))
                elif action.startswith("shelf:open:"):
                    index = int(action.split(":open:", 1)[1]
                                .split("|", 1)[0])
                    if button == 3:
                        self._send_shelf(index)
                    else:
                        self._open_shelf_item(action)
                else:
                    self._activate(action)
                return True
        return False

    def _activate(self, action):
        if action.startswith("shelf:open:"):
            self._open_shelf_item(action)
        if action == "activity":
            row = self._activity
            open_cmd = (row or {}).get("open")
            if open_cmd:
                subprocess.Popen(["sh", "-c", open_cmd],
                                 start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                self.shell.desktop_clicked()
            return
        if action in ("previous", "play-pause", "next", "shuffle", "love"):
            _playerctl(action)
            self.refresh()
        elif action == "clipboard":
            self.shell.open_clipboard()
        elif action == "focus":
            self.shell.open_focus_menu()
        elif action == "timer":
            self._toggle_timer()
        elif action == "screenshot":
            subprocess.Popen([SCREENSHOT, "region"], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif action == "assistant":
            self.shell.assistant.open("ask")
        elif action == "dictation":
            state.toggle_dictation()
            self.refresh()
        elif action == "phonehub":
            state.toggle_phonehub()
            self.refresh()
        elif action == "shuffle":
            _playerctl("shuffle")
            self.refresh()
        elif action == "like":
            _playerctl("love")
            self.refresh()
