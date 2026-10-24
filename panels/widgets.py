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


def _uptime():
    """How long the machine has been switched on, the way macOS spells it."""
    try:
        with open("/proc/uptime") as fh:
            seconds = int(float(fh.read().split()[0]))
    except (OSError, ValueError):
        return ""
    minutes = seconds // 60
    hours, minutes = divmod(minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


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
        self._weather = state.weather()
        self._report = state.weather_report()
        self._uptime = _uptime()
        self.redraw()

    def content_height(self):
        m = self.metrics
        return int(m.px("widget_size") * 3 + m.px("widget_gap") * 4
                   + m.px("widget_screen_h"))

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        size = m.px("widget_size")
        gap = m.px("widget_gap")
        radius = m.px("widget_radius")

        # top row: the analog clock (left) and the weather (right), the way
        # macOS stacks the clocks and the weather side by side
        self._tile(cr, 0, 0, width, size, radius, pal)
        self._paint_analog_clock(cr, 0, 0, size, size, pal)
        self._paint_weather(cr, size + gap, 0, width - size - gap, size, pal)

        # the month of the machine, laid out over the whole width
        cal_y = size + gap
        self._tile(cr, 0, cal_y, width, size, radius, pal)
        self._paint_calendar(cr, 0, cal_y, width, size, pal)

        # the three gauges
        gauge_y = cal_y + size + gap
        self._tile(cr, 0, gauge_y, width, size, radius, pal)
        self._paint_gauges(cr, 0, gauge_y, width, size, pal)

        # the screen time, and how long the machine has been on
        time_y = gauge_y + size + gap
        time_h = m.px("widget_screen_h")
        self._tile(cr, 0, time_y, width, time_h, radius, pal)
        self._paint_screen_time(cr, 0, time_y, width, time_h, pal)

    def _paint_weather(self, cr, x, y, w, h, pal):
        """The weather where the machine is, with the forecast below."""
        m = self.metrics
        text = getattr(self, "_weather", "")
        report = getattr(self, "_report", None)
        if not report and not text:
            draw.draw_text(cr, x + 10 * m.scale, y + h / 2, "The weather",
                           10 * m.scale, pal["text_faint"], baseline="middle")
            return
        if report:
            place = report.get("place") or ""
            condition = report.get("condition") or ""
            temperature = report.get("temp") or ""
            low, high = report.get("min", ""), report.get("max", "")
            forecast = report.get("forecast") or []
        else:
            # the short line the dock shows: "Orogbum: Patchy rain nearby +26C"
            place, _, rest = text.partition(":")
            place = place.split(",")[0].strip()
            condition, _, temperature = rest.strip().partition(" ")
            temperature = temperature.strip().lstrip("+").rstrip("C")
            low = high = ""
            forecast = []

        pad = 10 * m.scale
        big = h * 0.28
        temp_w = 0.0
        # the big temperature on the right, the way the weather widget
        # of macOS leans its number against the edge
        if temperature:
            temp_w = draw.text_width(cr, f"{temperature}°", big, "bold")
            draw.draw_text(cr, x + w - pad, y + h * 0.30, f"{temperature}°",
                           big, pal["text"], weight="bold", align="right",
                           baseline="middle")
        if low and high:
            draw.draw_text(cr, x + w - pad, y + h * 0.52, f"{high}/{low}",
                           9 * m.scale, pal["text_faint"], align="right",
                           baseline="middle")
        # ... the place and the condition on the left, kept clear of the
        # temperature
        text_w = max(0.0, w - temp_w - pad * 3)
        draw.draw_text(cr, x + pad, y + h * 0.15, place, 8 * m.scale,
                       pal["text_faint"], baseline="middle",
                       max_width=text_w, ellipsize=True)
        draw.draw_text(cr, x + pad, y + h * 0.36, condition, 9 * m.scale,
                       pal["text"], weight="bold", baseline="middle",
                       max_width=text_w, ellipsize=True)
        # the forecast strip along the bottom: the day, then high and low
        if forecast:
            strip_y = y + h * 0.80
            days = forecast[:4]
            cell = w / len(days)
            for index, day in enumerate(days):
                cx = x + pad + cell * index
                draw.draw_text(cr, cx, strip_y, day.get("dow", ""),
                               8 * m.scale, pal["text_faint"],
                               baseline="middle")
                draw.draw_text(
                    cr, x + pad + cell * (index + 1), strip_y,
                    f"{day.get('max', '')}/{day.get('min', '')}",
                    9 * m.scale, pal["text_dim"], align="right",
                    baseline="middle",
                    max_width=cell - pad * 2, ellipsize=True)

    def _paint_analog_clock(self, cr, x, y, w, h, pal):
        """The face of a watch, with the second hand of the moment."""
        m = self.metrics
        cx, cy = x + w / 2, y + h * 0.44
        radius = w * 0.40

        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        # the twelve marks of the dial
        for index in range(12):
            angle = index * math.pi / 6
            heavy = index % 3 == 0
            r0 = radius * (0.78 if heavy else 0.86)
            r1 = radius * 0.94
            cr.set_source_rgba(*pal["text"])
            cr.set_line_width(radius * (0.055 if heavy else 0.03))
            cr.move_to(cx + math.sin(angle) * r0, cy - math.cos(angle) * r0)
            cr.line_to(cx + math.sin(angle) * r1, cy - math.cos(angle) * r1)
            cr.stroke()

        now = datetime.datetime.now()
        # the hands: hour, minute, second
        hour_angle = (now.hour % 12 + now.minute / 60.0) * math.pi / 6
        minute_angle = (now.minute + now.second / 60.0) * math.pi / 30
        second_angle = now.second * math.pi / 30
        for angle, length, width, color in (
                (hour_angle, 0.46, 0.075, pal["text"]),
                (minute_angle, 0.68, 0.055, pal["text"]),
                (second_angle, 0.76, 0.02, pal["accent"])):
            cr.set_line_width(max(1.2, radius * width))
            cr.set_source_rgba(*color)
            cr.move_to(cx - math.sin(angle) * radius * length * 0.18,
                       cy + math.cos(angle) * radius * length * 0.18)
            cr.line_to(cx + math.sin(angle) * radius * length,
                       cy - math.cos(angle) * radius * length)
            cr.stroke()
        # the pin
        r_ = radius * 0.075
        draw.fill_squircle(cr, cx - r_, cy - r_, r_ * 2, r_ * 2, r_,
                           pal["accent"], 2.0)
        # the date of today under the face, the way the widget ends
        draw.draw_text(cr, cx, y + h * 0.92, now.strftime("%a %-d %b"),
                       h * 0.075, pal["text_faint"],
                       align="center", baseline="middle")
        cr.restore()

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
