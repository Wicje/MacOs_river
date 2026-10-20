"""The widget column.

macOS Tahoe stacks widgets under the menu bar on the left edge: a two column
grid of square widgets with a wide widget underneath.  This module renders
the same arrangement -- a calendar tile, a clock tile and a wide gauge tile.
"""

from __future__ import annotations

import calendar
import datetime
import math
import os

import gi

gi.require_version("Gtk", "3.0")

import cairo  # noqa: E402
from gi.repository import GLib  # noqa: E402

from ..macui import draw, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402


def _cpu_percent():
    try:
        with open("/proc/stat") as fh:
            for line in fh:
                if line.startswith("cpu "):
                    parts = [int(v) for v in line.split()[1:]]
                    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                    total = sum(parts)
                    return int(100 * (1 - idle / total)) if total else 0
    except (OSError, ValueError, ZeroDivisionError):
        pass
    return 0


def _mem_percent():
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0])
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        return int(100 * (1 - available / total)) if total else 0
    except (OSError, ValueError, ZeroDivisionError):
        return 0


def _disk_percent(path="/"):
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        return int(100 * (1 - free / total)) if total else 0
    except OSError:
        return 0


class Widgets(Panel):
    NAMESPACE = "mac-widgets"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="bottom",
            anchors={"top": True, "left": True},
            margins={"top": int(metrics.px("menu_bar_height")) + 10, "left": 10},
        )
        self.shell = shell
        self._values = {"cpu": 0, "mem": 0, "disk": 0}
        self.set_content_size(int(metrics.px("widget_width")), self.content_height())
        self.refresh()

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._values = {
            "cpu": _cpu_percent(),
            "mem": _mem_percent(),
            "disk": _disk_percent(),
        }
        self._screen_time = state.screen_time()
        self.redraw()

    def content_height(self):
        m = self.metrics
        return int(m.px("widget_size") * 2 + m.px("widget_gap")
                   + m.px("widget_screen_h"))

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        size = m.px("widget_size")
        gap = m.px("widget_gap")
        radius = m.px("widget_radius")

        # top row: calendar (left) and clock (right)
        self._tile(cr, 0, 0, size, size, radius, pal)
        self._paint_calendar(cr, 0, 0, size, size, pal)
        self._tile(cr, size + gap, 0, size, size, radius, pal)
        self._paint_clock(cr, size + gap, 0, size, size, pal)

        # bottom row: one wide tile with the system gauges
        wide_y = size + gap
        self._tile(cr, 0, wide_y, width, size, radius, pal)
        self._paint_gauges(cr, 0, wide_y, width, size, pal)

        # the screen time, the widget macOS Tahoe added
        time_y = wide_y + size + gap
        time_h = m.px("widget_screen_h")
        self._tile(cr, 0, time_y, width, time_h, radius, pal)
        self._paint_screen_time(cr, 0, time_y, width, time_h, pal)

    def _paint_screen_time(self, cr, x, y, w, h, pal):
        """How long every application was in the foreground today."""
        m = self.metrics
        rows = getattr(self, "_screen_time", [])[:3]
        draw.draw_text(cr, x + 12 * m.scale, y + 16 * m.scale, "Screen Time",
                       9 * m.scale, pal["text_faint"], weight="bold",
                       baseline="middle")
        if not rows:
            draw.draw_text(cr, x + 12 * m.scale, y + h * 0.58,
                           "Nothing to show yet", 9 * m.scale, pal["text_faint"],
                           baseline="middle")
            return
        biggest = max(minutes for _name, minutes in rows) or 1
        row_y = y + 32 * m.scale
        for name, minutes in rows:
            label = name if len(name) < 18 else name[:17] + "…"
            draw.draw_text(cr, x + 12 * m.scale, row_y, label, 9 * m.scale,
                           pal["text_dim"], baseline="middle")
            bar_x = x + 100 * m.scale
            bar_w = w - 150 * m.scale
            draw.fill_squircle(cr, bar_x, row_y - 3 * m.scale, bar_w,
                               6 * m.scale, 3 * m.scale, pal["fill_hover"], 2.0)
            draw.fill_squircle(cr, bar_x, row_y - 3 * m.scale,
                               max(6 * m.scale, bar_w * minutes / biggest),
                               6 * m.scale, 3 * m.scale, pal["accent"], 2.0)
            draw.draw_text(cr, x + w - 12 * m.scale, row_y,
                           f"{minutes}m", 9 * m.scale, pal["text_dim"],
                           align="right", baseline="middle")
            row_y += 22 * m.scale

    def _tile(self, cr, x, y, w, h, radius, pal):
        draw.glass_panel(cr, x, y, w, h, radius, pal,
                         exponent=self.metrics.squareness, shadow=True,
                         shadow_spread=12, shadow_alpha=0.24, tint=1.2)

    # -- tiles ----------------------------------------------------------------

    def _paint_clock(self, cr, x, y, w, h, pal):
        now = datetime.datetime.now()
        draw.draw_text(cr, x + w / 2, y + h * 0.40, now.strftime("%H:%M"),
                       h * 0.235, pal["text"], weight="bold",
                       align="center", baseline="middle")
        draw.draw_text(cr, x + w / 2, y + h * 0.63, now.strftime("%a %-d %b"),
                       h * 0.095, pal["text_dim"],
                       align="center", baseline="middle")

    def _paint_calendar(self, cr, x, y, w, h, pal):
        today = datetime.date.today()
        pad = w * 0.09

        draw.draw_text(cr, x + w / 2, y + h * 0.155, today.strftime("%B").upper(),
                       h * 0.093, pal["text_dim"], weight="bold",
                       align="center", baseline="middle")

        cols = 7
        cell = (w - pad * 2) / cols
        head_y = y + h * 0.30

        for index, name in enumerate(("M", "T", "W", "T", "F", "S", "S")):
            cx = x + pad + index * cell + cell / 2
            draw.draw_text(cr, cx, head_y, name, h * 0.072,
                           pal["text_faint"], align="center", baseline="middle")

        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(today.year,
                                                                    today.month)
        grid_top = y + h * 0.38
        grid_h = h * 0.55
        row_h = min(grid_h / max(len(weeks), 1), cell * 0.98)

        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                cx = x + pad + c * cell + cell / 2
                cy = grid_top + row_h * 0.5 + r * row_h
                if day == today.day:
                    r_ = cell * 0.38
                    draw.fill_squircle(cr, cx - r_, cy - r_, r_ * 2, r_ * 2, r_,
                                       pal["accent"], 2.0)
                    draw.draw_text(cr, cx, cy, str(day), h * 0.075,
                                   pal["on_accent"], weight="bold",
                                   align="center", baseline="middle")
                else:
                    draw.draw_text(cr, cx, cy, str(day), h * 0.075,
                                   pal["text_dim"], align="center",
                                   baseline="middle")

    def _paint_gauges(self, cr, x, y, w, h, pal):
        gauges = [
            ("CPU", self._values["cpu"]),
            ("MEM", self._values["mem"]),
            ("DISK", self._values["disk"]),
        ]
        cell = w / len(gauges)
        radius = min(cell * 0.25, h * 0.21)
        cy = y + h * 0.34
        for index, (label, value) in enumerate(gauges):
            cx = x + cell * (index + 0.5)
            self._paint_gauge(cr, cx, cy, radius, value, label, pal)

    def _paint_gauge(self, cr, cx, cy, radius, value, label, pal):
        start = math.radians(135)
        extent = math.radians(270)
        width = radius * 0.17

        cr.save()
        cr.set_line_width(width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        # new_sub_path keeps cairo from joining the two arcs with a line
        cr.new_sub_path()
        cr.set_source_rgba(*pal["fill_hover"])
        cr.arc(cx, cy, radius, start, start + extent)
        cr.stroke()

        ratio = max(0.0, min(1.0, value / 100.0))
        if ratio > 0:
            cr.new_sub_path()
            cr.set_source_rgba(*pal["accent"])
            cr.arc(cx, cy, radius, start, start + extent * ratio)
            cr.stroke()
        cr.restore()

        draw.draw_text(cr, cx, cy - radius * 0.10, f"{value}",
                       radius * 0.52, pal["text"], weight="bold",
                       align="center", baseline="middle")
        draw.draw_text(cr, cx, cy + radius + width * 2.4, label,
                       radius * 0.28, pal["text_faint"],
                       align="center", baseline="middle")
