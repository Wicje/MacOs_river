"""The widget strip above the dock.

A row of glass widget cards floats just above the dock, the way the
macOS widget shelf carries its pieces: the clock and the dial, the
weather, the calendar day, the media, the battery of the charge and a
sticky note.  The gallery adds cards and takes them away; the strip lays
the enabled ones out side by side, each one in its own glass card.
"""

from __future__ import annotations

import datetime
import math
import os
import subprocess

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, GtkLayerShell  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ART_CACHE = "/tmp/macshell-art-strip"
TODO_FILE = os.path.expanduser("~/.config/macshell/TODO.md")

ART = {"url": None, "pixbuf": None}

KINDS = ("clock", "analog", "weather", "calendar", "media",
         "battery", "sticky")
LABELS = {
    "clock": "Clock",
    "analog": "Analog clock",
    "weather": "Weather",
    "calendar": "Calendar",
    "media": "Now playing",
    "battery": "Battery",
    "sticky": "Sticky note",
}
# the widths of the cards, at scale 1.0
WIDTHS = {
    "clock": 132,
    "analog": 66,
    "weather": 150,
    "calendar": 132,
    "media": 244,
    "battery": 96,
    "sticky": 168,
}


def enabled_widgets(config):
    """The enabled kinds, in the order the strip lays them down."""
    wanted = config.get("dock_widgets")
    if not isinstance(wanted, list):
        wanted = ["clock", "analog", "weather"]
    return [kind for kind in KINDS if kind in wanted]


# -- the painters ------------------------------------------------------------
#
# Every painter paints one card in its box; the strip and the gallery both
# call them.


def _hairline(cr, x, y, w, h, radius, pal):
    cr.set_source_rgba(1.0, 1.0, 1.0, 0.10)
    cr.set_line_width(1.0)
    cr.stroke()


def _card(cr, x, y, w, h, m, pal, radius=None):
    s = h / 66.0
    radius = 16 * s if radius is None else radius
    draw.glass_panel(cr, x, y, w, h, radius, pal,
                     exponent=m.squareness, shadow=True,
                     shadow_spread=10, shadow_alpha=0.24, tint=1.2)
    draw.rounded_path(cr, x + 0.5, y + 0.5, w - 1, h - 1, radius - 0.5)
    _hairline(cr, x, y, w, h, radius, pal)


def _clock(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    now = ctx.get("now") or datetime.datetime.now()
    pad = 13 * s
    draw.draw_text(cr, x + pad, y + h * 0.36, now.strftime("%H:%M"),
                   20 * s, pal["text"], weight="bold", baseline="middle")
    draw.draw_text(cr, x + pad, y + h * 0.74, now.strftime("%a, %-d %b"),
                   9 * s, pal["text_dim"], baseline="middle")


def _analog(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    cx, cy = x + w / 2, y + h * 0.46
    radius = min(w, h * 1.45) * 0.40
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for index in range(12):
        angle = index * math.pi / 6
        heavy = index % 3 == 0
        r0 = radius * (0.74 if heavy else 0.84)
        r1 = radius * 0.92
        cr.set_source_rgba(*pal["text"])
        cr.set_line_width(radius * (0.10 if heavy else 0.055))
        cr.move_to(cx + math.sin(angle) * r0, cy - math.cos(angle) * r0)
        cr.line_to(cx + math.sin(angle) * r1, cy - math.cos(angle) * r1)
        cr.stroke()
    now = ctx.get("now") or datetime.datetime.now()
    hour_angle = (now.hour % 12 + now.minute / 60.0) * math.pi / 6
    minute_angle = (now.minute + now.second / 60.0) * math.pi / 30
    second_angle = now.second * math.pi / 30
    for angle, length, width, color in (
            (hour_angle, 0.46, 0.085, pal["text"]),
            (minute_angle, 0.66, 0.062, pal["text"]),
            (second_angle, 0.74, 0.03, (0.98, 0.23, 0.19, 1.0))):
        cr.set_line_width(max(1.2, radius * width * 1.4))
        cr.set_source_rgba(*color)
        cr.move_to(cx - math.sin(angle) * radius * length * 0.18,
                   cy + math.cos(angle) * radius * length * 0.18)
        cr.line_to(cx + math.sin(angle) * radius * length,
                   cy - math.cos(angle) * radius * length)
        cr.stroke()
    r_ = radius * 0.085
    draw.fill_squircle(cr, cx - r_, cy - r_, r_ * 2, r_ * 2, r_,
                       (0.98, 0.23, 0.19, 1.0), 2.0)
    cr.restore()


def _weather(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    pack = ctx.get("weather_pack") or ("", "", "", "", "")
    place, condition, temperature, low, high = pack
    glyphs.sun(cr, x + 13 * s, y + 15 * s, 17 * s, pal["text"])
    draw.draw_text(cr, x + 13 * s, y + h - 16 * s, condition or place,
                   9 * s, pal["text_faint"], baseline="middle",
                   max_width=w - 26 * s, ellipsize=True)
    if temperature:
        draw.draw_text(cr, x + w - 12 * s, y + h * 0.34, f"{temperature}°",
                       19 * s, pal["text"], weight="bold", align="right",
                       baseline="middle")
    if low and high:
        draw.draw_text(cr, x + w - 12 * s, y + h * 0.68, f"{high}/{low}",
                       9.5 * s, pal["text_dim"], align="right",
                       baseline="middle")


def _calendar(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    now = ctx.get("now") or datetime.datetime.now()
    draw.draw_text(cr, x + w / 2, y + 18 * s, now.strftime("%b %a").upper(),
                   9 * s, (0.97, 0.30, 0.28, 1.0), weight="bold",
                   align="center", baseline="middle")
    draw.draw_text(cr, x + w / 2, y + h * 0.60, str(now.day),
                   25 * s, pal["text"], weight="bold", align="center",
                   baseline="middle")


def _media(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    media = ctx.get("media")
    pad = 9 * s
    art = h - pad * 2
    art_x, art_y = x + pad, y + pad
    draw.fill_squircle(cr, art_x, art_y, art, art, 10 * s,
                       pal["fill_hover"], m.squareness)
    pixbuf = ctx.get("art")
    if pixbuf is not None:
        pw, ph = pixbuf.get_width(), pixbuf.get_height()
        factor = max(art / max(pw, ph), 0.0001)
        cr.save()
        cr.translate(art_x + (art - pw * factor) / 2,
                     art_y + (art - ph * factor) / 2)
        cr.scale(factor, factor)
        cr.set_source_pixbuf(pixbuf)
        cr.paint()
        cr.restore()
    else:
        title_fallback = ((media or ("?",))[0] or "?")
        draw.draw_text(cr, art_x + art / 2, art_y + art / 2,
                       (title_fallback[0] or "?").upper(), art * 0.4,
                       pal["text_dim"], weight="bold", align="center",
                       baseline="middle")
    if not media:
        draw.draw_text(cr, art_x + art + 11 * s, y + h / 2,
                       "Nothing playing", 10.5 * s, pal["text_dim"],
                       baseline="middle", max_width=w - art - 30 * s)
        return
    title, artist, status, position, length, _url = media
    text_x = art_x + art + 11 * s
    text_w = w - (text_x - x) - 62 * s
    draw.draw_text(cr, text_x, y + 19 * s, title or "", 12.5 * s,
                   pal["text"], weight="bold", baseline="middle",
                   max_width=text_w, ellipsize=True)
    draw.draw_text(cr, text_x, y + 37 * s, artist or "", 10 * s,
                   pal["text_dim"], baseline="middle",
                   max_width=text_w, ellipsize=True)
    bar_x = text_x
    bar_w = w - 66 * s - bar_x + x
    bar_y = y + h - 15 * s
    draw.fill_squircle(cr, bar_x, bar_y - 1.5 * s, bar_w, 3 * s,
                       1.5 * s, pal["fill_hover"], 2.0)
    if length:
        ratio = max(0.0, min(1.0, position / length))
        draw.fill_squircle(cr, bar_x, bar_y - 1.5 * s, bar_w * ratio,
                           3 * s, 1.5 * s, pal["accent"], 2.0)
    playing = (status or "").lower() == "playing"
    cy = y + h - 15 * s
    controls = (("prev", w - 54 * s, 9 * s),
                ("play", w - 30 * s, 11 * s),
                ("next", w - 12 * s, 9 * s))
    half = 11 * s
    for action, cx, size in controls:
        _play_shape(cr, x + cx - size / 2, cy - size / 2, size, action,
                    playing, pal, s)
        buttons.append((f"media:{action}", x + cx - half, cy - half,
                        half * 2.4, half * 2))


def _play_shape(cr, x, y, size, action, playing, pal, s):
    color = pal["text"]
    cr.save()
    cr.set_source_rgba(*color)
    if action == "prev":
        for offset in (0.0, size * 0.52):
            bx = x + size - offset - size * 0.46
            cr.move_to(bx + size * 0.46, y)
            cr.line_to(bx, y + size / 2)
            cr.line_to(bx + size * 0.46, y + size)
            cr.close_path()
            cr.fill()
    elif action == "next":
        for offset in (0.0, size * 0.52):
            bx = x + offset
            cr.move_to(bx, y)
            cr.line_to(bx + size * 0.46, y + size / 2)
            cr.line_to(bx, y + size)
            cr.close_path()
            cr.fill()
    elif action == "play":
        if playing:
            for offset in (0.18, 0.62):
                bx = x + offset * size
                cr.rectangle(bx, y, size * 0.2, size)
                cr.fill()
        else:
            cr.move_to(x + size * 0.30, y)
            cr.line_to(x + size * 0.30, y + size)
            cr.line_to(x + size * 0.86, y + size / 2)
            cr.close_path()
            cr.fill()
    cr.restore()


def _battery(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    level = ctx.get("battery")
    if level is None:
        draw.draw_text(cr, x + 13 * s, y + h / 2, "—", 14 * s,
                       pal["text_dim"], baseline="middle")
        return
    glyphs.battery(cr, x + 13 * s, y + h * 0.5 - 11 * s, 23 * s,
                   pal["text_dim"], level=level / 100.0,
                   charging=bool(ctx.get("charging")))
    draw.draw_text(cr, x + 44 * s, y + h / 2, f"{level}%", 14 * s,
                   pal["text"], weight="bold", baseline="middle")


def _sticky(ctx, cr, x, y, w, h, m, pal, buttons):
    s = h / 66.0
    cr.save()
    draw.rounded_path(cr, x, y, w, h, 16 * s)
    cr.set_source_rgba(0.97, 0.84, 0.36, 0.94)
    cr.fill()
    cr.restore()
    lines = ctx.get("sticky_lines") or ["Pick up coffee"]
    dark = (0.28, 0.23, 0.05, 1.0)
    soft = (0.55, 0.47, 0.16, 1.0)
    row_y = y + 17 * s
    for index, line in enumerate(lines[:3]):
        draw.draw_text(cr, x + 11 * s, row_y, line, 10.5 * s,
                       dark if index == 0 else soft,
                       weight="bold" if index == 0 else "normal",
                       baseline="middle", max_width=w - 22 * s,
                       ellipsize=True)
        row_y += 16 * s
    if len(lines) > 3:
        draw.draw_text(cr, x + w - 11 * s, row_y, f"+{len(lines) - 3}",
                       9 * s, soft, align="right", baseline="middle")


PAINTERS = {
    "clock": _clock,
    "analog": _analog,
    "weather": _weather,
    "calendar": _calendar,
    "media": _media,
    "battery": _battery,
    "sticky": _sticky,
}


def paint_card(kind, ctx, cr, x, y, w, h, m, pal, buttons=None, framed=True):
    """One card of the strip, drawn by its painter.

    ``framed`` gives the card its own glass and shadow; the cards that
    live inside the dock shelf paint flat, one tile on the shelf.
    """
    if framed:
        _card(cr, x, y, w, h, m, pal)
    else:
        radius = 16 * (h / 66.0)
        draw.fill_squircle(cr, x, y, w, h, radius,
                           pal["fill_hover"], m.squareness)
        draw.stroke_squircle(cr, x, y, w, h, radius,
                             (*pal["text_faint"][:3], 0.18), 1.0,
                             m.squareness)
    buttons = buttons if buttons is not None else []
    PAINTERS[kind](ctx, cr, x, y, w, h, m, pal, buttons)
    return buttons


def total_width(kinds, m):
    gap = m.px("strip_gap")
    widths = [int(WIDTHS[kind] * m.scale) for kind in kinds]
    return sum(widths) + gap * max(0, len(widths) - 1)


def _sticky_note():
    """The lines of the sticky note: the first open item of the day."""
    lines = []
    try:
        with open(TODO_FILE, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("- [ ]"):
                    lines.append(line[5:].strip().lstrip(" "))
                elif line and not line.startswith(("#", "-")):
                    lines.append(line)
    except OSError:
        pass
    return lines[:4] or ["Pick up coffee"]


def _load_art(url):
    """The cover of the piece being played, cached while it stays the same."""
    if not url:
        ART["pixbuf"] = None
        return
    if url == ART["url"]:
        return
    ART["url"] = url
    path = None
    if url.startswith("file://"):
        path = url[7:]
    elif url.startswith("http"):
        path = f"{ART_CACHE}.img"
        subprocess.Popen(["curl", "-fsSL", "--max-time", "4", url,
                          "-o", path],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    ART["pixbuf"] = None
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            ART["pixbuf"] = GdkPixbuf.Pixbuf.new_from_file_at_size(
                path, 96, 96)
        except Exception:
            pass


def snapshot_ctx(m):
    """Everything the card painters read, gathered once per tick."""
    now = datetime.datetime.now()
    report = state.weather_report()
    pack = ["", "", "", "", ""]
    if report:
        pack = [report.get("place") or "", report.get("condition") or "",
                report.get("temp") or "", report.get("min") or "",
                report.get("max") or ""]
    if not pack[2]:
        text = state.weather() or ""
        place, _, rest = text.partition(":")
        condition, _, temperature = rest.strip().partition(" ")
        pack = [place.split(",")[0].strip(), condition,
                temperature.strip().lstrip("+").rstrip("C"), "", ""]
    media = state.now_playing()
    _load_art(media[5] if media else None)
    return {
        "now": now,
        "media": media,
        "art": ART["pixbuf"],
        "battery": state.battery_level(),
        "charging": state.battery_charging(),
        "weather_pack": tuple(pack),
        "sticky_lines": _sticky_note(),
    }


# -- the clicks the cards carry ----------------------------------------------

def card_click(shell, kind):
    """What the empty face of a card does when it is clicked."""
    if kind in ("clock", "calendar"):
        shell.notification_centre.toggle()
        return
    if kind == "media":
        return
    # the empty face of a card edits the widgets
    shell.widget_gallery.toggle_visible()


def button_click(shell, ctx, action):
    """The buttons of the media card: the player knows them."""
    if action in ("media:play", "media:prev", "media:next"):
        command = action.split(":", 1)[1]
        if command == "play":
            media = ctx.get("media")
            playing = bool(media) and \
                (media[2] or "").lower() == "playing"
            command = "pause" if playing else "play-pause"
        subprocess.Popen(["playerctl", command],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
