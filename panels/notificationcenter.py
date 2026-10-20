"""The notification centre.

macOS slides a panel out of the right edge when the clock is clicked: the
calendar and the clock at the top, the notifications below.  This panel does
the same and lists the notifications mako has collected.
"""

from __future__ import annotations

import calendar
import datetime
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

WIDTH = 320
NOTIFICATION_LIMIT = 8


def _notifications():
    """The notifications mako has shown."""
    try:
        out = subprocess.run(["makoctl", "history"], capture_output=True,
                             text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return []
    if not out:
        return []
    items = []
    for chunk in out.split("\x1e"):
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        summary = lines[0].strip()
        body = " ".join(line.strip() for line in lines[1:]).strip()
        if summary or body:
            items.append((summary, body))
    return items[-NOTIFICATION_LIMIT:]


class NotificationCentre(Panel):
    NAMESPACE = "mac-notification-centre"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "right": True, "bottom": True},
            margins={"top": int(metrics.px("menu_bar_height")), "right": 0},
        )
        self.shell = shell
        self._notifications: list = []
        self._rows: list = []
        self.set_content_size(int(metrics.px("WIDTH") if False else metrics.px("menu_width") * 1.5),
                              400)
        self.refresh()

    # -- lifecycle -----------------------------------------------------------

    def refresh(self):
        self._notifications = _notifications()
        self.redraw()

    def open(self):
        self.refresh()
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
        pad = 16 * m.scale

        # a darker scrim so the content stays readable over any wallpaper
        cr.set_source_rgba(0.02, 0.02, 0.03, 0.55)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        draw.glass_panel(cr, 0, 0, width, height, 20 * m.scale, pal,
                         exponent=m.squareness, shadow=True, shadow_spread=18)

        # clock
        now = datetime.datetime.now()
        draw.draw_text(cr, width / 2, 52 * m.scale, now.strftime("%a %-d %b"),
                       m.font("menu_font_size") * 1.25, pal["text_dim"],
                       align="center", baseline="middle")
        draw.draw_text(cr, width / 2, 88 * m.scale, now.strftime("%H:%M"),
                       m.font("menu_font_size") * 3.4, pal["text"],
                       align="center", baseline="middle")

        # mini calendar
        cal_h = 132 * m.scale
        cal_y = 124 * m.scale
        draw.fill_squircle(cr, pad, cal_y, width - pad * 2, cal_h, 14 * m.scale,
                           pal["fill"], m.squareness)
        self._paint_calendar(cr, pad, cal_y, width - pad * 2, cal_h, pal)

        # notifications
        y = cal_y + cal_h + 16 * m.scale
        self._rows = []
        if not self._notifications:
            draw.draw_text(cr, width / 2, y + 30 * m.scale, "No Notifications",
                           m.font("cc_font_size"), pal["text_faint"],
                           align="center", baseline="middle")
            return
        for summary, body in self._notifications:
            row_h = 54 * m.scale
            if y + row_h > height - pad:
                break
            draw.fill_squircle(cr, pad, y, width - pad * 2, row_h - 6 * m.scale,
                               12 * m.scale, pal["fill"], m.squareness)
            draw.draw_text(cr, pad + 12 * m.scale, y + 16 * m.scale, summary,
                           m.font("cc_font_size_bold"), pal["text"],
                           weight="bold", baseline="middle",
                           max_width=width - pad * 2 - 24 * m.scale,
                           ellipsize=True)
            if body:
                draw.draw_text(cr, pad + 12 * m.scale, y + 34 * m.scale, body,
                               m.font("cc_font_size"), pal["text_dim"],
                               baseline="middle",
                               max_width=width - pad * 2 - 24 * m.scale,
                               ellipsize=True)
            self._rows.append((y, row_h))
            y += row_h

    def _paint_calendar(self, cr, x, y, w, h, pal):
        m = self.metrics
        today = datetime.date.today()
        cell = (w - 24 * m.scale) / 7
        head_y = y + 16 * m.scale
        for index, name in enumerate(("M", "T", "W", "T", "F", "S", "S")):
            cx = x + 12 * m.scale + index * cell + cell / 2
            draw.draw_text(cr, cx, head_y, name, 9 * m.scale, pal["text_faint"],
                           align="center", baseline="middle")
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(today.year,
                                                                    today.month)
        row_h = min((h - 34 * m.scale) / max(len(weeks), 1), cell * 0.95)
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                cx = x + 12 * m.scale + c * cell + cell / 2
                cy = y + 34 * m.scale + row_h * 0.5 + r * row_h
                if day == today.day:
                    radius = cell * 0.36
                    draw.fill_squircle(cr, cx - radius, cy - radius,
                                       radius * 2, radius * 2, radius,
                                       pal["accent"], 2.0)
                    draw.draw_text(cr, cx, cy, str(day), 10 * m.scale,
                                   pal["on_accent"], weight="bold",
                                   align="center", baseline="middle")
                else:
                    draw.draw_text(cr, cx, cy, str(day), 10 * m.scale,
                                   pal["text_dim"], align="center",
                                   baseline="middle")
