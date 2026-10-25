"""System Settings.

A macOS style settings window: a sidebar with the sections and a content
area with the controls.  Everything is written to the shell's config file,
so the changes show up immediately.
"""

from __future__ import annotations

import os
import subprocess

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
    ("centre", "Control Centre", "control_center"),
    ("sound", "Sound", "speaker"),
    ("displays", "Displays", "display"),
    ("wifi", "Wi-Fi", "wifi"),
    ("battery", "Battery", "battery"),
    ("notifications", "Notifications", "bell"),
    ("keyboard", "Keyboard", "keyboard"),
    ("about", "About", "apple"),
]

UTILITIES = [
    ("accessibility", "accessibility"),
    ("appearance", "moon"),
    ("launchpad", "grid"),
    ("spotlight", "spotlight"),
    ("stage", "grid"),
    ("nightshift", "moon"),
    ("wallpaper", "display"),
    ("settings", "grid"),
    ("mirror", "airplay"),
    ("display", "display"),
    ("sound", "speaker"),
]

NOTCH_ACTIONS = [
    ("clipboard", "clipboard", "Clipboard"),
    ("focus", "moon", "Focus"),
    ("screenshot", "camera", "Screenshot"),
    ("assistant", "sparkles", "Ask"),
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
            keyboard=False,
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
        # the window already carries the drawing area (a bin takes one
        # child), so the entry goes into an overlay the way Launchpad does
        overlay = Gtk.Overlay()
        self.remove(self.area)
        overlay.add(self.area)
        overlay.add_overlay(self._entry)
        self.add(overlay)

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
            if glyph == "battery":
                glyphs.battery(cr, x + 18 * scale,
                               iy + (item_h - size * 0.68) / 2,
                               size * 0.68, color,
                               (self._battery_level() or 0) / 100.0,
                               self._battery_charging())
            else:
                self._draw_glyph(cr, glyph, x + 18 * scale,
                                 iy + (item_h - size) / 2, size, color)
            draw.draw_text(cr, x + 42 * scale, iy + item_h / 2 - 2 * scale, label,
                           m.font("menu_font_size"), color, baseline="middle",
                           max_width=sidebar - 56 * scale, ellipsize=True)

        # the traffic lights
        light = 12 * scale
        lx = x + 16 * scale
        ly = y + 16 * scale
        for index, colour in enumerate(((1.0, 0.23, 0.19), (1.0, 0.62, 0.0),
                                        (0.30, 0.80, 0.20))):
            cx = lx + index * (light + 7 * scale)
            draw.fill_squircle(cr, cx, ly, light, light, light / 2,
                               (*colour, 0.92), 2.0)
            self._rows.append((cx, ly, light, light,
                                lambda _x=None, index=index: self._light(index)))

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
        elif self.section == "centre":
            self._paint_centre(cr, x, top, w, scale, pal)
        elif self.section == "sound":
            self._paint_sound(cr, x, top, w, scale, pal)
        elif self.section == "displays":
            self._paint_displays(cr, x, top, w, scale, pal)
        elif self.section == "wifi":
            self._paint_wifi(cr, x, top, w, scale, pal)
        elif self.section == "battery":
            self._paint_battery(cr, x, top, w, scale, pal)
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

        # the Liquid Glass controls of macOS
        draw.draw_text(cr, x, y, "Liquid Glass", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 24 * scale

        opacity = float(cfg.get("glass_opacity", 1.0))
        draw.draw_text(cr, x, y, "Opacity", 11 * scale, pal["text"], baseline="middle")
        self._slider(cr, x + 110 * scale, y, w - 180 * scale, scale, pal,
                     int((opacity - 0.5) / 1.0 * 100),
                     lambda value: self._set("glass_opacity",
                                             round(0.5 + value / 100.0, 2)))
        draw.draw_text(cr, x + w, y, f"{round(opacity * 100)}%", 11 * scale,
                       pal["text_dim"], align="right", baseline="middle")
        y += 38 * scale

        tint = float(cfg.get("glass_tint", 0.0))
        draw.draw_text(cr, x, y, "Tint", 11 * scale, pal["text"], baseline="middle")
        self._slider(cr, x + 110 * scale, y, w - 180 * scale, scale, pal,
                     int(tint * 100),
                     lambda value: self._set("glass_tint",
                                             round(value / 100.0, 2)))
        draw.draw_text(cr, x + w, y, f"{round(tint * 100)}%", 11 * scale,
                       pal["text_dim"], align="right", baseline="middle")
        y += 44 * scale

        self._switch_row(cr, x, y, w, scale, pal, "Reduce transparency",
                         "reduce_transparency", False)

    def _paint_desktop(self, cr, x, y, w, scale, pal):
        m = self.metrics
        cfg = self._config()
        y += 8 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Show the Dock",
                         "show_dock", True, action=self.shell.sync_dock)
        y += 38 * scale
        self._segment_row(cr, x, y, w, scale, pal, "Dock behaviour", "dock_mode",
                          (("always", "Always"), ("desktop", "Desktop"),
                           ("auto", "Auto")),
                          "desktop", action=self.shell.sync_dock)
        y += 38 * scale
        self._switch_row(cr, x, y, w, scale, pal, "Show the notch",
                         "show_notch", True, action=self.shell.sync_notch)
        y += 38 * scale
        self._segment_row(cr, x, y, w, scale, pal, "Notch behaviour", "notch_mode",
                          (("always", "Always"), ("auto", "Auto")),
                          "auto", action=self.shell.sync_notch)
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

    def _paint_centre(self, cr, x, y, w, scale, pal):
        """Which tiles the Control Centre shows, and what the notch carries."""
        m = self.metrics
        cfg = self._config()

        draw.draw_text(cr, x, y, "The tiles of the Control Centre", 11 * scale,
                       pal["text_faint"], baseline="middle")
        y += 26 * scale
        tiles = cfg.get("cc_tiles") or [uid for uid, _g in UTILITIES]
        y = self._tile_grid(cr, x, y, w, scale, pal, tiles, "cc_tiles",
                            [uid for uid, _g in UTILITIES], UTILITIES)
        y += 24 * scale

        draw.draw_text(cr, x, y, "The buttons of the notch", 11 * scale,
                       pal["text_faint"], baseline="middle")
        y += 26 * scale
        actions = cfg.get("notch_actions") or [a for a, _g, _l in NOTCH_ACTIONS]
        self._tile_grid(cr, x, y, w, scale, pal, actions, "notch_actions",
                        [a for a, _g, _l in NOTCH_ACTIONS], NOTCH_ACTIONS)

    def _tile_grid(self, cr, x, y, w, scale, pal, chosen, key, all_ids,
                   all_entries):
        """A grid of small buttons, each one a switch."""
        m = self.metrics
        size = 30 * scale
        gap = 8 * scale
        per_row = max(1, int((w + gap) / (size + gap)))
        for index, entry in enumerate(all_entries):
            uid, glyph = entry[0], entry[1]
            title = entry[2] if len(entry) > 2 else uid
            col = index % per_row
            row = index // per_row
            bx = x + col * (size + gap)
            by = y + row * (size + gap + 14 * scale)
            on = uid in chosen
            draw.fill_squircle(cr, bx, by, size, size, 7 * scale,
                               pal["accent"] if on else pal["fill_hover"], 2.0)
            self._draw_glyph(cr, glyph, bx + size * 0.24, by + size * 0.24,
                             size * 0.52,
                             pal["on_accent"] if on else pal["text_dim"])
            label = title if len(title) <= 8 else title[:7] + "…"
            draw.draw_text(cr, bx + size / 2, by + size + 9 * scale, label,
                           8 * scale,
                           pal["text"] if on else pal["text_faint"],
                           align="center", baseline="middle",
                           max_width=size + 12 * scale, ellipsize=True)
            self._rows.append((bx, by, size, size,
                                lambda _x=None, uid=uid, key=key, chosen=list(chosen):
                                self._flip_tile(key, uid, chosen)))
        rows = (len(all_entries) + per_row - 1) // per_row
        return y + rows * (size + gap + 14 * scale)

    def _flip_tile(self, key, uid, chosen):
        """Turn a tile on or off."""
        if uid in chosen:
            new = [item for item in chosen if item != uid]
        else:
            new = list(chosen) + [uid]
        self._set(key, new)
        if key == "cc_tiles":
            self.shell.control_centre.refresh()
        if key == "notch_actions":
            self.shell.notch.redraw()

    def _paint_sound(self, cr, x, y, w, scale, pal):
        m = self.metrics
        cfg = self._config()
        y += 8 * scale

        # output
        draw.draw_text(cr, x, y, "Output", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 24 * scale
        draw.draw_text(cr, x, y, "Built-in Speakers — HD Audio",
                       m.font("cc_font_size"), pal["text"],
                       baseline="middle")
        y += 32 * scale
        self._slider(cr, x, y, w - 120 * scale, scale, pal, state.volume(),
                     lambda value: state.set_volume(value))
        y += 44 * scale
        self._switch_state_row(cr, x, y, w, scale, pal, "Mute",
                               state.muted(), lambda: state.toggle_mute())
        y += 44 * scale

        # the sounds of the shell itself (startup, trash, screenshot…)
        self._switch_row(cr, x, y, w, scale, pal, "Interface sounds",
                         "sounds", True)
        y += 36 * scale
        if cfg.get("sounds", True):
            sv = int(float(cfg.get("sound_volume", 0.7)) * 100)
            draw.draw_text(cr, x, y, "Sounds volume", m.font("cc_font_size"),
                           pal["text"], baseline="middle")
            self._slider(cr, x + 110 * scale, y, w - 230 * scale, scale, pal,
                         sv, lambda value: self._set("sound_volume",
                                                     round(value / 100.0, 2)))
        y += 50 * scale

        # input
        draw.draw_text(cr, x, y, "Input", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 24 * scale
        draw.draw_text(cr, x, y, "Built-in Microphone",
                       m.font("cc_font_size"), pal["text"], baseline="middle")
        y += 36 * scale
        talks = state.dictation_active()
        self._switch_state_row(cr, x, y, w, scale, pal, "Dictation",
                               talks, lambda: state.toggle_dictation())

    def _paint_displays(self, cr, x, y, w, scale, pal):
        m = self.metrics
        y += 8 * scale
        draw.draw_text(cr, x, y, "Brightness", m.font("cc_font_size"),
                       pal["text"], baseline="middle")
        self._slider(cr, x + 110 * scale, y, w - 230 * scale, scale, pal,
                     state.brightness(),
                     lambda value: state.set_brightness(value))
        y += 44 * scale
        self._switch_state_row(cr, x, y, w, scale, pal, "Night Light",
                               state.nightlight_on(),
                               lambda: state.toggle_nightlight())
        y += 44 * scale
        info = actions.system_info()
        draw.draw_text(cr, x, y, f"Resolution {info['display']}",
                       m.font("cc_font_size"), pal["text_dim"],
                       baseline="middle")

    def _paint_wifi(self, cr, x, y, w, scale, pal):
        m = self.metrics
        y += 8 * scale
        on = state.wifi_enabled()
        self._switch_state_row(cr, x, y, w, scale, pal, "Wi-Fi", on,
                               lambda: state.toggle_wifi())
        y += 48 * scale
        if not on:
            draw.draw_text(cr, x, y, "Wi-Fi is off.", m.font("cc_font_size"),
                           pal["text_faint"], baseline="middle")
            return
        ssid = state.wifi_ssid()
        strength = state.wifi_strength()
        draw.draw_text(cr, x, y, "Connected" if ssid else "No network",
                       11 * scale, pal["text_faint"], baseline="middle")
        y += 30 * scale
        glyphs.wifi(cr, x, y - 9 * scale, 15 * scale, pal["text"],
                    level=3 if strength >= 66 else 2 if strength >= 33 else 1)
        draw.draw_text(cr, x + 24 * scale, y, ssid or "—",
                       m.font("cc_font_size"), pal["text"], baseline="middle",
                       max_width=w - 130 * scale, ellipsize=True)
        draw.draw_text(cr, x + w, y, f"{strength}%",
                       m.font("cc_font_size"), pal["text_dim"],
                       align="right", baseline="middle")

    def _paint_battery(self, cr, x, y, w, scale, pal):
        m = self.metrics
        level = self._battery_level()
        y += 8 * scale
        if level is None:
            draw.draw_text(cr, x, y, "No battery found.",
                           m.font("cc_font_size"), pal["text_faint"],
                           baseline="middle")
        else:
            charging = self._battery_charging()
            glyphs.battery(cr, x, y - 12 * scale, 24 * scale, pal["text"],
                           level / 100.0, charging)
            draw.draw_text(cr, x + 34 * scale, y,
                           f"{level}% — "
                           + ("Charging" if charging else "On battery"),
                           m.font("cc_font_size"), pal["text"],
                           baseline="middle")
        y += 44 * scale
        draw.draw_text(cr, x, y, "Frontmost today", 11 * scale,
                       pal["text_faint"], baseline="middle")
        y += 28 * scale
        rows = state.screen_time()
        if not rows:
            draw.draw_text(cr, x, y, "Nothing counted yet today.",
                           m.font("cc_font_size"), pal["text_faint"],
                           baseline="middle")
            return
        top = max((minutes for _name, minutes in rows), default=1) or 1
        for name, minutes in rows:
            width = max(4 * scale, (w - 170 * scale) * minutes / top)
            draw.fill_squircle(cr, x, y - 7 * scale, width, 14 * scale,
                               4 * scale, pal["fill_hover"], 2.0)
            if width > 46 * scale:
                draw.draw_text(cr, x + 8 * scale, y,
                               state.friendly_name(name),
                               m.font("cc_font_size") * 0.9, pal["text"],
                               baseline="middle", max_width=width - 16 * scale,
                               ellipsize=True)
            label = (f"{minutes // 60} h {minutes % 60} m"
                     if minutes >= 60 else f"{minutes} m")
            draw.draw_text(cr, x + w, y, label, m.font("cc_font_size"),
                           pal["text_dim"], align="right", baseline="middle")
            y += 26 * scale

    def _paint_notifications(self, cr, x, y, w, scale, pal):
        m = self.metrics
        y += 8 * scale
        self._switch_state_row(cr, x, y, w, scale, pal, "Do Not Disturb",
                               state.dnd_on(), lambda: state.toggle_dnd())
        y += 44 * scale
        recent = self._recent_notifications()
        draw.draw_text(cr, x, y, "Latest", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 26 * scale
        if not recent:
            draw.draw_text(cr, x, y, "No notifications recorded.",
                           m.font("cc_font_size"), pal["text_faint"],
                           baseline="middle")
            return
        for summary, body in recent:
            dot = 5 * scale
            draw.fill_squircle(cr, x, y - dot / 2, dot, dot, dot / 2,
                               pal["accent"], 2.0)
            line = f"{summary} — {body}" if body else summary
            draw.draw_text(cr, x + 14 * scale, y, line,
                           m.font("cc_font_size") * 0.95, pal["text_dim"],
                           baseline="middle", max_width=w - 20 * scale,
                           ellipsize=True)
            y += 24 * scale

    def _recent_notifications(self):
        """The last notifications mako kept, fresh on every open."""
        try:
            out = subprocess.run(
                ["makoctl", "history"], capture_output=True, text=True,
                timeout=3).stdout.strip()
        except Exception:  # noqa: BLE001
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
        return items[:5]

    def _paint_keyboard(self, cr, x, y, w, scale, pal):
        m = self.metrics
        cfg = self._config()
        y += 8 * scale

        # the machine's real repeat behaviour, fed straight to river
        draw.draw_text(cr, x, y, "Key repeat", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 26 * scale
        delay = int(cfg.get("key_repeat_delay", 600))
        draw.draw_text(cr, x, y, "Delay until repeat", m.font("cc_font_size"),
                       pal["text"], baseline="middle")
        self._slider(cr, x + 140 * scale, y, w - 260 * scale, scale, pal,
                     int((1.0 - (delay - 200) / 1000.0) * 100),
                     lambda value: self._apply_repeat(
                         200 + int((1.0 - value / 100.0) * 1000), delay))
        draw.draw_text(cr, x + w, y, f"{delay} ms",
                       m.font("cc_font_size") * 0.9, pal["text_dim"],
                       align="right", baseline="middle")
        y += 36 * scale
        rate = int(cfg.get("key_repeat_rate", 25))
        draw.draw_text(cr, x, y, "Repeat rate", m.font("cc_font_size"),
                       pal["text"], baseline="middle")
        self._slider(cr, x + 140 * scale, y, w - 260 * scale, scale, pal,
                     int((rate - 5) / 55.0 * 100),
                     lambda value: self._apply_repeat(
                         delay, 5 + int(value / 100.0 * 55)))
        draw.draw_text(cr, x + w, y, f"{rate} cps",
                       m.font("cc_font_size") * 0.9, pal["text_dim"],
                       align="right", baseline="middle")
        y += 48 * scale

        draw.draw_text(cr, x, y, "Shortcuts", 11 * scale, pal["text_faint"],
                       baseline="middle")
        y += 26 * scale
        for keys, label in SHORTCUTS:
            draw.draw_text(cr, x, y, keys, m.font("cc_font_size") * 0.9,
                           pal["text_dim"], baseline="middle")
            draw.draw_text(cr, x + 190 * scale, y, label,
                           m.font("cc_font_size") * 0.9, pal["text"],
                           baseline="middle")
            y += 23 * scale

    def _apply_repeat(self, delay, rate):
        """Write the repeat behaviour down and tell river to use it."""
        self._set("key_repeat_delay", max(200, min(1200, int(delay))))
        self._set("key_repeat_rate", max(5, min(60, int(rate))))
        state.spawn(f"riverctl set-repeat {int(rate)} {int(delay)}")

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

    def _battery_level(self):
        return state.battery_level()

    def _battery_charging(self):
        return state.battery_charging()

    def _switch_state_row(self, cr, x, y, w, scale, pal, label, on, flip):
        """A switch whose state comes from the machine, not the config."""
        m = self.metrics
        draw.draw_text(cr, x, y, label, m.font("cc_font_size"), pal["text"],
                       baseline="middle")
        switch_w = 38 * scale
        switch_h = 22 * scale
        sx = x + w - switch_w
        sy = y - switch_h / 2
        draw.fill_squircle(cr, sx, sy, switch_w, switch_h, switch_h / 2,
                           pal["accent"] if on else pal.get(
                               "switch_off", pal["fill_hover"]), 2.0)
        knob = switch_h - 4 * scale
        kx = sx + switch_w - knob - 2 * scale if on else sx + 2 * scale
        draw.fill_squircle(cr, kx, sy + 2 * scale, knob, knob, knob / 2,
                           pal["on_accent"], 2.0)
        self._rows.append((sx, sy, switch_w, switch_h, lambda _x=None: flip()))

    def _switch_row(self, cr, x, y, w, scale, pal, label, key, default=True,
                    action=None):
        m = self.metrics
        cfg = self._config()
        value = cfg.get(key, default)
        if isinstance(default, str):
            # a string setting is a switch between two states
            on = value != default
        else:
            on = value
        draw.draw_text(cr, x, y, label, m.font("cc_font_size"), pal["text"],
                       baseline="middle")
        switch_w = 38 * scale
        switch_h = 22 * scale
        sx = x + w - switch_w
        sy = y - switch_h / 2
        draw.fill_squircle(cr, sx, sy, switch_w, switch_h, switch_h / 2,
                           pal["accent"] if on else pal.get(
                               "switch_off", pal["fill_hover"]), 2.0)
        knob = switch_h - 4 * scale
        kx = sx + switch_w - knob - 2 * scale if on else sx + 2 * scale
        draw.fill_squircle(cr, kx, sy + 2 * scale, knob, knob, knob / 2,
                           pal["on_accent"], 2.0)
        if isinstance(default, str):
            other = "auto" if default == "always" else "always"
            def _flip(_x=None, key=key, other=other, action=action):
                self._set(key, other)
                if action:
                    action()
        else:
            def _flip(_x=None, key=key, action=action):
                self._toggle(key)
                if action:
                    action()
        self._rows.append((sx, sy, switch_w, switch_h, _flip))

    def _segment_row(self, cr, x, y, w, scale, pal, label, key, options,
                     default, action=None):
        """A row of small buttons, the way macOS offers a choice."""
        m = self.metrics
        cfg = self._config()
        current = cfg.get(key, default)
        draw.draw_text(cr, x, y, label, m.font("cc_font_size"), pal["text"],
                       baseline="middle")
        btn_w = 76 * scale
        btn_h = 22 * scale
        gap = 6 * scale
        bx = x + w - (len(options) * btn_w + (len(options) - 1) * gap)
        by = y - btn_h / 2
        for index, (value, title) in enumerate(options):
            cx = bx + index * (btn_w + gap)
            active = current == value
            draw.fill_squircle(cr, cx, by, btn_w, btn_h, btn_h / 2,
                               pal["accent"] if active else pal["fill_hover"],
                               2.0)
            draw.draw_text(cr, cx + btn_w / 2, y, title,
                           m.font("cc_font_size"),
                           pal["on_accent"] if active else pal["text"],
                           align="center", baseline="middle")
            self._rows.append((cx, by, btn_w, btn_h,
                                lambda _x=None, value=value: self._pick(key, value,
                                                                        action)))

    def _pick(self, key, value, action=None):
        self._set(key, value)
        if action:
            action()

    def _slider(self, cr, x, y, w, scale, pal, value, callback):
        m = self.metrics
        height = 18 * scale
        draw.fill_squircle(cr, x, y, w, height, height / 2, pal["fill_hover"], 2.0)
        fill = max(height * 0.999, w * (value / 100.0))
        draw.fill_squircle(cr, x, y, fill, height, height / 2, pal["accent"], 2.0)
        self._rows.append((x, y - 8 * scale, w, height + 16 * scale,
                            lambda cx: callback(int(max(0, min(100, (cx - x) / w * 100))))))

    def _light(self, index):
        """The red, yellow and green buttons."""
        if index == 0:
            self.close()
        elif index == 1:
            self.hide()
        else:
            self.toggle_size()

    def toggle_size(self):
        """Make the window bigger, the way the green button does."""
        m = self.metrics
        big = 1.4
        width = int(WIDTH * m.scale * big)
        height = int(HEIGHT * m.scale * big)
        screen_w = m.width or 1366
        screen_h = m.height or 768
        self.set_content_size(width, height)
        self.set_position(int((screen_w - width) / 2),
                          int((screen_h - height) / 2))
        self.redraw()

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
