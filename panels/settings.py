"""System Settings.

A macOS style settings window: a sidebar with the sections and a content
area with the controls.  Everything is written to the shell's config file,
so the changes show up immediately.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from ..macui import actions, draw, glyphs, state  # noqa: E402
from ..macui.metrics import ACCENTS  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

WIDTH = 780
HEIGHT = 520
SIDEBAR = 196

SECTIONS = [
    ("appearance", "Appearance", "grid"),
    ("desktop", "Desktop & Dock", "display"),
    ("sound", "Sound", "speaker"),
    ("displays", "Displays", "display"),
    ("notifications", "Notifications", "check"),
    ("keyboard", "Keyboard", "chevron_down"),
    ("about", "About", "apple"),
]

SHORTCUTS = [
    ("Super + D", "Launchpad"),
    ("Super + Space", "Spotlight"),
    ("Super + C", "Control Centre"),
    ("Super + Tab", "Mission Control"),
    ("Super + Shift + A", "Apple menu"),
    ("Super + Shift + T", "Hide the Dock"),
    ("Super + Shift + Q", "Hide the notch"),
    ("Super + Shift + G", "Hide the widgets"),
    ("Super + 1 … 9", "Switch workspace"),
    ("Super + Shift + 1 … 9", "Move the window"),
    ("Super + Q / W / M", "Close / minimise the window"),
    ("Super + Ctrl + Left / Right", "Tile the window"),
]


class Settings(Panel):
    NAMESPACE = "mac-settings"

    def __init__(self, metrics, shell):
        # a floating window, so the rest of the desktop stays usable
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=True,
        )
        self.shell = shell
        self.section = "appearance"
        self._rows: list = []
        self._switches: list = []
        width = int(WIDTH * metrics.scale)
        height = int(HEIGHT * metrics.scale)
        screen_w = metrics.width or 1366
        screen_h = metrics.height or 768
        self.set_content_size(width, height)
        self.set_position(int((screen_w - width) / 2),
                          int((screen_h - height) / 2))
        self._entry = Gtk.Entry()
        self._entry.set_can_focus(True)
        self._entry.set_no_show_all(True)
        self.add(self._entry)

    # -- lifecycle -----------------------------------------------------------

    def open(self):
        self.show_all()
        self._entry.grab_focus()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self):
        if self.get_visible():
            self.close()
        else:
            self.open()

    # -- helpers -------------------------------------------------------------

    def _config(self):
        return self.metrics.config

    def _set(self, key, value):
        self._config()[key] = value
        self.metrics.save()
        self.redraw()

    def _toggle(self, key):
        self._set(key, not self._config().get(key, True))

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        # the window
        w = width
        h = height
        x = 0
        y = 0
        # an opaque window, the way System Settings looks
        cr.save()
        draw.rounded_path(cr, x, y, w, h, 12 * scale)
        cr.clip()
        dark = self.metrics.config.get("theme", "dark") == "dark"
        cr.set_source_rgba(0.09, 0.09, 0.11, 1.0 if dark else 0.99)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgba(0.5, 0.5, 0.55, 0.06 if dark else 0.04)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.restore()
        draw.stroke_squircle(cr, x, y, w, h, 12 * scale, pal["separator"],
                             1.0, self.metrics.squareness)

        # the sidebar
        sidebar = SIDEBAR * scale
        cr.save()
        draw.rounded_path(cr, x, y, w, h, 12 * scale)
        cr.clip()
        cr.rectangle(x, y, sidebar, h)
        cr.set_source_rgba(0.5, 0.5, 0.55, 0.10)
        cr.fill()
        cr.restore()

        self._rows = []
        self._switches = []

        item_h = 34 * scale
        for index, (key, label, glyph) in enumerate(SECTIONS):
            iy = y + 18 * scale + index * item_h
            if key == self.section:
                draw.fill_squircle(cr, x + 10 * scale, iy, sidebar - 20 * scale,
                                   item_h - 4 * scale, 7 * scale,
                                   pal["accent"], self.metrics.squareness)
                color = pal["on_accent"]
            else:
                color = pal["text"]
            size = 15 * scale
            self._draw_glyph(cr, glyph, x + 18 * scale, iy + (item_h - size) / 2,
                             size, color)
            draw.draw_text(cr, x + 42 * scale, iy + item_h / 2 - 2 * scale, label,
                           m.font("menu_font_size"), color, baseline="middle",
                           max_width=sidebar - 56 * scale, ellipsize=True)

        content_x = x + sidebar + 24 * scale
        content_w = w - sidebar - 48 * scale
        self._paint_content(cr, content_x, y + 20 * scale, content_w, h - 40 * scale)

    def _paint_content(self, cr, x, y, w, h):
        m = self.metrics
        pal = m.palette()
        scale = m.scale
        title = dict((key, label) for key, label, _ in SECTIONS)[self.section]
        draw.draw_text(cr, x, y + 12 * scale, title, m.font("menu_font_size") * 1.5,
                       pal["text"], weight="bold", baseline="middle")
        top = y + 42 * scale

        if self.section == "appearance":
            self._paint_appearance(cr, x, top, w, scale, pal)
        elif self.section == "desktop":
            self._paint_desktop(cr, x, top, w, scale, pal)
        elif self.section == "sound":
            self._paint_sound(cr, x, top, w, scale, pal)
        elif self.section == "displays":
            self._paint_displays(cr, x, top, w, scale, pal)
        elif self.section == "notifications":
            self._paint_notifications(cr, x, top, w, scale, pal)
        elif self.section == "keyboard":
            self._paint_keyboard(cr, x, top, w, scale, pal)
        elif self.section == "about":
            self._paint_about(cr, x, top, w, scale, pal)

    # -- sections ------------------------------------------------------------

    def _paint_appearance(self, cr, x, y, w, scale, pal):
        m = self.metrics
        cfg = self._config()
        y += 8 * scale

        # light / dark
        for index, (mode, label) in enumerate((("light", "Light"),
                                               ("dark", "Dark"))):
            bx = x + index * 110 * scale
            active = cfg.get("theme", "dark") == mode
            draw.fill_squircle(cr, bx, y, 96 * scale, 28 * scale, 7 * scale,
                               pal["accent"] if active else pal["fill_hover"],
                               self.metrics.squareness)
            draw.draw_text(cr, bx + 48 * scale, y + 14 * scale, label,
                           m.font("cc_font_size"),
                           pal["on_accent"] if active else pal["text"],
                           align="center", baseline="middle")
            self._rows.append((bx, y, 96 * scale, 28 * scale,
                                lambda _x=None, mode=mode: self._set("theme", mode)))
        y += 52 * scale

        # accent colours
        draw.draw_text(cr, x, y, "Accent colour", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 26 * scale
        swatch = 24 * scale
        for index, (name, colour) in enumerate(ACCENTS.items()):
            bx = x + index * (swatch + 10 * scale)
            active = cfg.get("accent", "blue") == name
            draw.fill_squircle(cr, bx, y, swatch, swatch, swatch / 2,
                               (*colour, 1.0), 2.0)
            if active:
                draw.stroke_squircle(cr, bx - 3 * scale, y - 3 * scale,
                                     swatch + 6 * scale, swatch + 6 * scale,
                                     (swatch + 6 * scale) / 2,
                                     pal["text_dim"], 1.5, 2.0)
            self._rows.append((bx, y, swatch, swatch,
                                lambda _x=None, name=name: self._set("accent", name)))
        y += 52 * scale

        self._switch_row(cr, x, y, w, scale, pal, "Reduce transparency",
                         "reduce_transparency", False)

    def _paint_desktop(self, cr, x, y, w, scale, pal):
        m = self.metrics
        cfg = self._config()
        y += 8 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Show the Dock",
                         "show_dock", True, action=self.shell.sync_dock)
        y += 38 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Show the notch",
                         "show_notch", True, action=self.shell.sync_notch)
        y += 38 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Show the widgets",
                         "show_widgets", True, action=self.shell.sync_widgets)
        y += 48 * scale

        draw.draw_text(cr, x, y, "Wallpaper", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 30 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Change the wallpaper every 30 seconds",
                         "wallpaper_rotate", True, action=self.shell.restart_wallpaper)
        y += 44 * scale
        draw.draw_text(cr, x, y, "The wallpaper rotates through ~/mac and ~/Pictures/wall.",
                       m.font("cc_font_size"), pal["text_faint"], baseline="middle")

    def _paint_sound(self, cr, x, y, w, scale, pal):
        m = self.metrics
        volume = state.volume()
        y += 8 * scale
        self._slider(cr, x, y, w - 120 * scale, scale, pal, volume,
                     lambda value: state.set_volume(value))
        y += 44 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Mute", "mute", False,
                         action=lambda: state.toggle_mute())

    def _paint_displays(self, cr, x, y, w, scale, pal):
        m = self.metrics
        brightness = state.brightness()
        y += 8 * scale
        self._slider(cr, x, y, w - 120 * scale, scale, pal, brightness,
                     lambda value: state.set_brightness(value))
        y += 50 * scale
        info = actions.system_info()
        draw.draw_text(cr, x, y, f"Resolution {info['display']}",
                       m.font("cc_font_size"), pal["text_dim"], baseline="middle")

    def _paint_notifications(self, cr, x, y, w, scale, pal):
        m = self.metrics
        self._switch_row(cr, x, y + 10 * scale, w, scale, pal,
                         "Do Not Disturb", "dnd", False,
                         action=lambda: state.toggle_dnd())
        draw.draw_text(cr, x, y + 60 * scale,
                       "Notifications are shown by mako and collected in the "
                       "notification centre.", m.font("cc_font_size"),
                       pal["text_faint"], baseline="middle")

    def _paint_keyboard(self, cr, x, y, w, scale, pal):
        m = self.metrics
        for index, (keys, label) in enumerate(SHORTCUTS):
            ky = y + index * 26 * scale
            draw.draw_text(cr, x, ky, keys, m.font("cc_font_size"), pal["text_dim"],
                           baseline="middle")
            draw.draw_text(cr, x + 200 * scale, ky, label, m.font("cc_font_size"),
                           pal["text"], baseline="middle")

    def _paint_about(self, cr, x, y, w, scale, pal):
        m = self.metrics
        info = actions.system_info()
        rows = [
            ("Chip", info["cpu"]),
            ("Graphics", info["gpu"]),
            ("Memory", info["memory"]),
            ("Disk", info["disk"]),
            ("Display", info["display"]),
            ("Compositor", info["compositor"]),
            ("Kernel", info["kernel"]),
            ("Uptime", info["uptime"]),
        ]
        for index, (label, value) in enumerate(rows):
            ry = y + index * 26 * scale
            draw.draw_text(cr, x, ry, label, m.font("cc_font_size"),
                           pal["text_faint"], baseline="middle")
            draw.draw_text(cr, x + 120 * scale, ry, value, m.font("cc_font_size"),
                           pal["text"], baseline="middle",
                           max_width=w - 120 * scale, ellipsize=True)

    # -- widgets -------------------------------------------------------------

    def _switch_row(self, cr, x, y, w, scale, pal, label, key, default=True,
                    action=None):
        m = self.metrics
        cfg = self._config()
        on = cfg.get(key, default)
        draw.draw_text(cr, x, y, label, m.font("cc_font_size"), pal["text"],
                       baseline="middle")
        switch_w = 38 * scale
        switch_h = 22 * scale
        sx = x + w - switch_w
        sy = y - switch_h / 2
        draw.fill_squircle(cr, sx, sy, switch_w, switch_h, switch_h / 2,
                           pal["accent"] if on else pal["fill_hover"], 2.0)
        knob = switch_h - 4 * scale
        kx = sx + switch_w - knob - 2 * scale if on else sx + 2 * scale
        draw.fill_squircle(cr, kx, sy + 2 * scale, knob, knob, knob / 2,
                           pal["on_accent"], 2.0)
        self._rows.append((sx, sy, switch_w, switch_h,
                            lambda _x=None: (self._toggle(key), action and action())))

    def _slider(self, cr, x, y, w, scale, pal, value, callback):
        m = self.metrics
        height = 18 * scale
        draw.fill_squircle(cr, x, y, w, height, height / 2, pal["fill_hover"], 2.0)
        fill = max(height * 0.999, w * (value / 100.0))
        draw.fill_squircle(cr, x, y, fill, height, height / 2, pal["accent"], 2.0)
        self._rows.append((x, y - 8 * scale, w, height + 16 * scale,
                            lambda cx: callback(int(max(0, min(100, (cx - x) / w * 100))))))

    def _draw_glyph(self, cr, name, x, y, size, color):
        fn = getattr(glyphs, name, None)
        if fn is None:
            return
        fn(cr, x, y, size, color)

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        m = self.metrics
        scale = m.scale

        # the sidebar
        item_h = 34 * scale
        for index, (key, _label, _glyph) in enumerate(SECTIONS):
            iy = 18 * scale + index * item_h
            if 10 * scale <= x <= SIDEBAR * scale - 10 * scale \
                    and iy <= y <= iy + item_h - 4 * scale:
                self.section = key
                self.redraw()
                return True

        # the controls
        for rx, ry, rw, rh, action in self._rows:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                action(x)
                return True
        return False
