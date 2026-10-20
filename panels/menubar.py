"""The macOS menu bar.

A full-width translucent strip across the top of every workspace: the Apple
logo, the focused application's name, the standard application menus and
the status cluster on the right (Spotlight, Control Centre, Wi-Fi, battery
and the clock).
"""

from __future__ import annotations

import math
import os
import time

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui import actions, draw, glyphs, menus, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

def battery_level():
    for name in ("BAT0", "BAT1"):
        path = f"/sys/class/power_supply/{name}/capacity"
        try:
            with open(path) as fh:
                return int(fh.read().strip())
        except (OSError, ValueError):
            continue
    return None


class MenuBar(Panel):
    NAMESPACE = "mac-menubar"

    def __init__(self, metrics, shell):
        height = int(metrics.px("menu_bar_height"))
        super().__init__(
            metrics,
            layer="top",
            anchors={"top": True, "left": True, "right": True},
            exclusive=height,
        )
        self.shell = shell
        self.set_content_size(-1, height)
        self.bar_height = height
        self._items: list = []
        self._app_name = "Finder"
        self._app_id = ""
        self._battery = None
        self._charging = False
        self._media = None
        self._focused = ""

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._app_id = state.focused_app_id()
        self._app_name = state.focused_app() or "Finder"
        self._media = state.now_playing()
        self._focused = state.focused_window()
        self._battery = battery_level()
        try:
            with open("/sys/class/power_supply/BAT0/status") as fh:
                self._charging = "Charging" in fh.read()
        except OSError:
            self._charging = False
        self.redraw()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        s = m.scale

        bar = self.bar_height
        # translucent material so the compositor blur reads through
        cr.set_source_rgba(*pal["menu_bar"])
        cr.rectangle(0, 0, width, bar)
        cr.fill()
        cr.set_source_rgba(*pal["separator"])
        cr.rectangle(0, bar - 1, width, 1)
        cr.fill()

        pad = m.px("menu_pad_x")
        gap = m.px("menu_item_gap")
        font = m.font("menu_font_size")
        icon = m.px("apple_logo")

        self._items = []

        # Apple logo
        glyphs.apple(cr, pad, (bar - icon) / 2, icon, pal["text"])
        x = pad + icon + gap
        self._items.append({"name": "__apple__", "x": pad, "w": icon + gap})

        # focused application name (bold)
        name_w = draw.text_width(cr, self._app_name, font, "bold")
        draw.draw_text(cr, x, bar / 2, self._app_name, font, pal["text"],
                       weight="bold", baseline="middle")
        x += name_w + gap * 1.4
        self._items.append({"name": "__app__", "x": x, "w": name_w})

        # application menus, the ones the focused application would have
        for title, _items in menus.menus_for(self._app_id):
            w = draw.text_width(cr, title, font)
            draw.draw_text(cr, x, bar / 2, title, font, pal["text"],
                           baseline="middle")
            self._items.append({"name": title, "x": x, "w": w})
            x += w + gap

        # status cluster, right aligned
        right = width - pad
        glyph = m.px("status_glyph")

        clock_text = time.strftime("%a %-d %b  %H:%M")
        if self._battery is not None:
            clock_text = f"{self._battery}%  " + clock_text
        clock_w = draw.text_width(cr, clock_text, m.font("clock_font_size"))
        draw.draw_text(cr, right, bar / 2, clock_text, m.font("clock_font_size"),
                       pal["text"], align="right", baseline="middle")
        self._clock_x = right - clock_w
        self._clock_w = clock_w
        right -= clock_w + m.px("status_gap")

        if self._battery is not None:
            bh = 11 * s
            bw = 22 * s
            glyphs.battery(cr, right - bw, (bar - bh) / 2, bh,
                           pal["text"], self._battery / 100.0, self._charging)
            self._battery_x = right - bw
            self._battery_w = bw
            right -= bw + m.px("status_gap")

        wifi_on = state.wifi_enabled()
        wifi_color = pal["text"] if wifi_on else pal["text_faint"]
        glyphs.wifi(cr, right - glyph, (bar - glyph) / 2, glyph, wifi_color,
                    level=3)
        self._wifi_x = right - glyph
        right -= glyph + m.px("status_gap")

        glyphs.control_center(cr, right - glyph, (bar - glyph) / 2, glyph, pal["text"])
        self._cc_x = right - glyph
        right -= glyph + m.px("status_gap")

        glyphs.spotlight(cr, right - glyph, (bar - glyph) / 2, glyph, pal["text"])
        self._spotlight_x = right - glyph

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        # the menu bar covers the whole top of the screen, so it doubles as
        # the sensor that brings the notch back
        self.shell.pointer_moved("top", y)
        return False

    def on_click(self, x, y, button):
        m = self.metrics
        if hasattr(self, "_clock_x") and \
                self._clock_x <= x <= self._clock_x + self._clock_w:
            self.shell.toggle_notification_centre()
            return True
        if hasattr(self, "_battery_x") and \
                self._battery_x <= x <= self._battery_x + self._battery_w:
            self.shell.open_popup("battery", x)
            return True
        if hasattr(self, "_wifi_x") and \
                self._wifi_x <= x <= self._wifi_x + m.px("status_glyph"):
            self.shell.open_popup("wifi", x)
            return True
        if hasattr(self, "_cc_x") and self._cc_x <= x <= self._cc_x + m.px("status_glyph"):
            self.shell.toggle_control_center()
            return True
        if hasattr(self, "_spotlight_x") and \
                self._spotlight_x <= x <= self._spotlight_x + m.px("status_glyph"):
            self.shell.open_spotlight()
            return True
        for item in self._items:
            if item["x"] <= x <= item["x"] + item["w"]:
                name = item["name"]
                if name in ("__apple__", "__app__"):
                    self.shell.toggle_apple_menu(x)
                else:
                    for title, entries in menus.menus_for(self._app_id):
                        if title == name:
                            self.shell.open_menu(title, entries, x)
                            return True
        return False

    def on_scroll(self, x, y, direction):
        return False

    def open_menu_by_title(self, title):
        """Open one of the application menus by name."""
        for item in self._items:
            if item["name"] == title:
                for name, entries in menus.menus_for(self._app_id):
                    if name == title:
                        self.shell.open_menu(title, entries, item["x"])
                        return True
        return False
