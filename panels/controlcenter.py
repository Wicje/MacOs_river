"""The macOS Tahoe Control Centre.

Tahoe turned the Control Centre into a narrow, tall panel of glass pills
and circles: connectivity on the left, media and utilities on the right.
This module reproduces that arrangement.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui import actions, draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402


class ControlCentre(Panel):
    NAMESPACE = "mac-control-center"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "right": True},
            margins={"top": int(metrics.px("menu_bar_height")) + 6, "right": 8},
        )
        self.shell = shell
        self._regions = []
        self._media = None
        self.hover = None
        self.set_content_size(int(metrics.px("cc_width")),
                              int(self._height(int(metrics.px("cc_width")))))
        self.refresh()

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._media = state.now_playing()
        width = int(self.metrics.px("cc_width"))
        height = self._layout(width)
        self.set_content_size(width, int(height))
        self.redraw()

    # -- geometry ------------------------------------------------------------

    def _columns(self, width):
        m = self.metrics
        pad = m.px("cc_pad")
        gap = m.px("cc_col_gap")
        col = (width - pad * 2 - gap) / 2
        return pad, col, pad + col + gap

    def _layout(self, width):
        m = self.metrics
        pad = m.px("cc_pad")
        gap = m.px("cc_gap")
        left_x, col_w, right_x = self._columns(width)

        regions = []

        # -- now playing, across the top of the panel --------------------
        regions.append({
            "kind": "media", "x": left_x, "y": pad, "w": width - pad * 2,
            "h": m.px("cc_media_h"),
        })

        top = pad + m.px("cc_media_h") + m.px("cc_section_gap")

        # -- left column --------------------------------------------------
        y = top
        regions.append({
            "kind": "pill", "id": "wifi", "glyph": "wifi", "label": "Wi-Fi",
            "x": left_x, "y": y, "w": col_w, "h": m.px("cc_pill_h"),
        })
        y += m.px("cc_pill_h") + gap

        circle = m.px("cc_circle")
        regions.append({
            "kind": "circle", "id": "bluetooth", "glyph": "bluetooth",
            "label": "Bluetooth",
            "x": left_x, "y": y, "w": circle, "h": circle,
        })
        regions.append({
            "kind": "circle", "id": "stage", "glyph": "grid",
            "label": "Stage Manager",
            "x": left_x + circle + gap, "y": y, "w": circle, "h": circle,
        })
        y += circle + gap

        regions.append({
            "kind": "pill", "id": "focus", "glyph": "moon", "label": "Focus",
            "x": left_x, "y": y, "w": col_w, "h": m.px("cc_pill_h"),
        })
        y += m.px("cc_pill_h") + gap

        regions.append({
            "kind": "slider", "id": "bright", "glyph": "display",
            "label": "Brightness",
            "x": left_x, "y": y, "w": col_w, "h": m.px("cc_pill_h") + 12,
        })
        y += m.px("cc_pill_h") + 12 + gap

        regions.append({
            "kind": "slider", "id": "volume", "glyph": "speaker",
            "label": "Sound",
            "x": left_x, "y": y, "w": col_w, "h": m.px("cc_pill_h") + 12,
        })
        y += m.px("cc_pill_h") + 12

        left_bottom = y

        # -- right column -------------------------------------------------
        y = top
        for tile in ({"id": "airplay", "glyph": "airplay"},
                     {"id": "display", "glyph": "display"}):
            regions.append({
                "kind": "circle", "id": tile["id"], "glyph": tile["glyph"],
                "label": tile["id"],
                "x": right_x, "y": y, "w": circle, "h": circle,
            })
            right_x += circle + gap
        right_x = self._columns(width)[2]
        y += circle + m.px("cc_section_gap")

        utilities = [
            ("accessibility", "accessibility"),
            ("appearance", "moon"),
            ("launchpad", "grid"),
            ("spotlight", "spotlight"),
            ("stage", "grid"),
            ("nightshift", "moon"),
            ("wallpaper", "display"),
            ("settings", "grid"),
        ]
        small = m.px("cc_small_circle")
        for index, (uid, glyph) in enumerate(utilities):
            col = index % 2
            row = index // 2
            regions.append({
                "kind": "circle", "id": uid, "glyph": glyph, "label": uid,
                "x": right_x + col * (small + gap),
                "y": y + row * (small + gap),
                "w": small, "h": small,
            })
        y += 4 * (small + gap) - gap + m.px("cc_section_gap")

        # the power mode
        y += m.px("cc_section_gap")
        for index, mode in enumerate(("power-saver", "balanced",
                                      "performance")):
            width = (col_w - m.px("cc_button_gap") * 2) / 3
            regions.append({
                "kind": "power", "id": mode, "label": mode,
                "x": right_x + index * (width + m.px("cc_button_gap")),
                "y": y, "w": width, "h": 26,
            })
        y += 26

        regions.append({
            "kind": "exit", "x": right_x, "y": y, "w": col_w, "h": 26,
        })
        y += 26 + m.px("cc_gap")

        # lock and log out
        for index, (uid, label) in enumerate((("lock", "Lock Screen"),
                                              ("logout", "Log Out"))):
            width = (col_w - m.px("cc_button_gap")) / 2
            regions.append({
                "kind": "session", "id": uid, "label": label,
                "x": right_x + index * (width + m.px("cc_button_gap")),
                "y": y, "w": width, "h": 26,
            })
        y += 26

        right_bottom = y

        self._regions = regions
        return max(left_bottom, right_bottom) + pad

    def _height(self, width):
        return self._layout(width)

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        total = self._layout(width)
        # a dark layer under the glass, so the panel stays readable when a
        # busy window sits behind it
        dark = m.config.get("theme", "dark") == "dark"
        scrim = ((0.06, 0.06, 0.08, 0.60) if dark
                 else (1.0, 1.0, 1.0, 0.78))
        draw.scrim(cr, 0, 0, width, total, m.px("cc_radius"), scrim,
                   m.squareness)
        draw.glass_panel(cr, 0, 0, width, total, m.px("cc_radius"), pal,
                         exponent=m.squareness, shadow=True, shadow_spread=18)

        for region in self._regions:
            kind = region["kind"]
            if kind == "media":
                self._paint_media(cr, region, pal)
            elif kind == "slider":
                self._paint_slider(cr, region, pal)
            elif kind == "exit":
                self._paint_exit(cr, region, pal)
            elif kind == "power":
                self._paint_power(cr, region, pal)
            elif kind == "session":
                self._paint_session(cr, region, pal)
            elif kind == "circle":
                self._paint_circle(cr, region, pal)
            else:
                self._paint_pill(cr, region, pal)

    # -- pieces --------------------------------------------------------------

    def _paint_pill(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        radius = h / 2
        active = self._active(region["id"])
        hovered = self.hover is region
        if active:
            draw.fill_squircle(cr, x, y, w, h, radius, pal["accent"], m.squareness)
            color = pal["on_accent"]
        else:
            fill = pal["fill_hover"] if hovered else pal["fill"]
            draw.fill_squircle(cr, x, y, w, h, radius, fill, m.squareness)
            color = pal["text"]

        glyph = h * 0.42
        gx = x + h * 0.28
        gy = y + (h - glyph) / 2
        self._draw_glyph(cr, region["glyph"], gx, gy, glyph, color)

        label = region["label"]
        draw.draw_text(cr, gx + glyph + 8 * m.scale, y + h * 0.40, label,
                       m.font("cc_font_size_bold"), color, weight="bold",
                       baseline="middle")
        sub = self._subtitle(region["id"])
        if sub:
            draw.draw_text(cr, gx + glyph + 8 * m.scale, y + h * 0.68, sub,
                           m.font("cc_font_size"), pal["text_dim"],
                           baseline="middle")

    def _paint_circle(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        active = self._active(region["id"])
        if active:
            draw.fill_squircle(cr, x, y, w, h, w / 2, pal["accent"], 2.0)
            color = pal["on_accent"]
        else:
            fill = pal["fill_hover"] if self.hover is region else pal["fill"]
            draw.fill_squircle(cr, x, y, w, h, w / 2, fill, 2.0)
            color = pal["text"]
        glyph = w * 0.5
        self._draw_glyph(cr, region["glyph"], x + (w - glyph) / 2,
                         y + (h - glyph) / 2, glyph, color)

    def _paint_slider(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        radius = h / 2

        draw.fill_squircle(cr, x, y, w, h, radius, pal["fill"], m.squareness)

        label = region["label"]
        draw.draw_text(cr, x + 14 * m.scale, y + 14 * m.scale, label,
                       m.font("cc_font_size"), pal["text"], baseline="middle")

        value = state.brightness() if region["id"] == "bright" else state.volume()
        if region["id"] == "volume" and state.muted():
            value = 0

        track_h = 16 * m.scale
        track_y = y + h - track_h - 10 * m.scale
        track_x = x + 14 * m.scale
        track_w = w - 28 * m.scale

        draw.fill_squircle(cr, track_x, track_y, track_w, track_h,
                           track_h / 2, pal["fill_hover"], 2.0)
        fill_w = max(track_h * 0.999, track_w * (value / 100.0))
        draw.fill_squircle(cr, track_x, track_y, fill_w, track_h,
                           track_h / 2, pal["accent"], 2.0)

        glyph = 14 * m.scale
        gx = track_x + track_w - glyph - 4 * m.scale
        gy = track_y + (track_h - glyph) / 2
        self._draw_glyph(cr, region["glyph"], gx, gy, glyph, pal["text"])

        region["track"] = (track_x, track_y, track_w)

    def _paint_media(self, cr, region, pal):
        m = self.metrics
        art = 52 * m.scale
        x, y = region["x"], region["y"]
        w = region["w"]
        media = self._media

        art_x = x
        art_y = y + (region["h"] - art) / 2
        draw.fill_squircle(cr, art_x, art_y, art, art, art * 0.16,
                           pal["fill"], m.squareness)
        if media:
            draw.draw_text(cr, art_x + art / 2, art_y + art / 2,
                           (media[0] or "?")[0].upper(), art * 0.46,
                           pal["text"], weight="bold", align="center",
                           baseline="middle")
        else:
            glyphs.speaker(cr, art_x + art * 0.28, art_y + art * 0.28,
                           art * 0.44, pal["text_dim"])

        # the playback buttons on the right
        button = 26 * m.scale
        gap = 8 * m.scale
        bx = x + w - (3 * button + 2 * gap)
        by = y + (region["h"] - button) / 2
        region["buttons"] = []
        for action, shape in (("previous", "back"), ("play-pause", "play"),
                              ("next", "forward")):
            cr.save()
            cr.set_source_rgba(*pal["fill_hover"])
            cr.arc(bx + button / 2, by + button / 2, button / 2, 0,
                   2 * 3.14159)
            cr.fill()
            cr.restore()
            self._paint_play_glyph(cr, shape, bx + button / 2 - 6 * m.scale,
                                   by + button / 2 - 6 * m.scale, 12 * m.scale,
                                   pal["text"])
            region["buttons"].append((action, bx, by, button))
            bx += button + gap

        text_x = art_x + art + 12 * m.scale
        text_w = max(40 * m.scale,
                     region["buttons"][0][1] - text_x - 12 * m.scale)

        title = media[0] if media else "Not Playing"
        artist = media[1] if media else "—"
        draw.draw_text(cr, text_x, y + region["h"] * 0.38, title,
                       m.font("cc_font_size_bold"), pal["text"], weight="bold",
                       max_width=text_w, ellipsize=True)
        draw.draw_text(cr, text_x, y + region["h"] * 0.64, artist or "—",
                       m.font("cc_font_size"), pal["text_dim"],
                       max_width=text_w, ellipsize=True)

        if media and media[4]:
            ratio = max(0.0, min(1.0, media[3] / media[4]))
            track_y = y + region["h"] * 0.82
            draw.fill_squircle(cr, text_x, track_y, text_w, 3 * m.scale,
                               1.5 * m.scale, pal["fill_hover"], 2.0)
            draw.fill_squircle(cr, text_x, track_y, text_w * ratio,
                               3 * m.scale, 1.5 * m.scale, pal["accent"], 2.0)

    def _paint_play_glyph(self, cr, shape, x, y, size, color):
        """The little triangles of the playback buttons."""
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

    def _paint_power(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        current = state.power_mode()
        active = current == region["id"]
        draw.fill_squircle(cr, x, y, w, h, h / 2,
                           pal["accent"] if active else pal["fill"],
                           m.squareness)
        color = pal["on_accent"] if active else pal["text"]
        label = {"power-saver": "Eco", "balanced": "Balanced",
                 "performance": "Pro"}.get(region["id"], region["id"])
        draw.draw_text(cr, x + w / 2, y + h / 2, label,
                       m.font("cc_font_size"), color, align="center",
                       baseline="middle", max_width=w - 6, ellipsize=True)

    def _paint_session(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        draw.fill_squircle(cr, x, y, w, h, h / 2, pal["fill"], m.squareness)
        draw.draw_text(cr, x + w / 2, y + h / 2, region["label"],
                       m.font("cc_font_size"), pal["text"], align="center",
                       baseline="middle", max_width=w - 6, ellipsize=True)

    def _paint_exit(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        draw.fill_squircle(cr, x, y, w, h, h / 2, pal["fill_hover"], 2.0)
        draw.draw_text(cr, x + w / 2, y + h / 2, "Settings…",
                       m.font("cc_font_size"), pal["text_dim"],
                       align="center", baseline="middle")

    # -- helpers -------------------------------------------------------------

    def _draw_glyph(self, cr, name, x, y, size, color):
        fn = getattr(glyphs, name, None)
        if fn is None:
            return
        fn(cr, x, y, size, color)

    def _active(self, region_id):
        if region_id == "wifi":
            return state.wifi_enabled()
        if region_id == "bluetooth":
            return state.bluetooth_on()
        if region_id == "focus":
            return state.dnd_on()
        if region_id == "appearance":
            return state.theme_name() == "dark"
        return False

    def _subtitle(self, region_id):
        if region_id == "wifi":
            ssid = state.wifi_ssid()
            return ssid if ssid else ("On" if state.wifi_enabled() else "Off")
        if region_id == "focus":
            return "On" if state.dnd_on() else "Off"
        return ""

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        found = None
        for region in self._regions:
            if (region["x"] <= x <= region["x"] + region["w"]
                    and region["y"] <= y <= region["y"] + region["h"]):
                found = region
                break
        if found is not self.hover:
            self.hover = found
            self.redraw()
        return False

    def on_click(self, x, y, button):
        # the regions are rebuilt here as well, so a click never lands on a
        # stale (or empty) layout
        width = self.content_size()[0]
        if width >= 100:
            self._layout(width)
        for region in self._regions:
            if not (region["x"] <= x <= region["x"] + region["w"]
                    and region["y"] <= y <= region["y"] + region["h"]):
                continue
            kind = region["kind"]
            if kind == "media":
                if self._media_button(region, x, y):
                    return True
                continue
            if kind == "pill":
                self._activate(region["id"])
            elif kind == "circle":
                self._activate(region["id"])
            elif kind == "slider":
                self._set_slider(region, x)
            elif kind == "power":
                state.spawn(f"powerprofilesctl set {region['id']}")
            elif kind == "session":
                if region["id"] == "lock":
                    actions.lock_session()
                else:
                    actions.log_out()
            elif kind == "exit":
                self.shell.open_settings()
            return True
        return False

    def _media_button(self, region, x, y):
        """The playback buttons of the now playing card."""
        for action, bx, by, size in region.get("buttons", []):
            if bx <= x <= bx + size and by <= y <= by + size:
                subprocess.Popen(["playerctl", action], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                GLib.timeout_add(400, self.refresh)
                return True
        return False

    def _activate(self, region_id):
        if region_id == "wifi":
            # the networks list, the way macOS opens it
            self.shell.open_popup("wifi", self._columns(
                self.content_size()[0])[0])
        elif region_id == "bluetooth":
            self.shell.open_popup("bluetooth", self._columns(
                self.content_size()[0])[0])
        elif region_id == "focus":
            self.shell.open_focus_menu()
        elif region_id == "appearance":
            state.toggle_theme()
        elif region_id == "launchpad":
            self.shell.open_launchpad()
        elif region_id == "spotlight":
            self.shell.open_spotlight()
        elif region_id == "stage":
            self.shell.stage_manager.toggle()
        elif region_id == "nightshift":
            state.spawn(f"{os.path.expanduser('~/.config/river/nightlight.py')}")
        elif region_id == "wallpaper":
            state.spawn(f"{os.path.expanduser('~/.config/river/wallpaper-pick.sh')}")
        elif region_id == "settings":
            self.shell.open_settings()
        GLib.timeout_add(200, self.refresh)

    def _set_slider(self, region, x):
        track = region.get("track")
        if not track:
            return
        track_x, _track_y, track_w = track
        ratio = max(0.0, min(1.0, (x - track_x) / track_w))
        value = int(ratio * 100)
        if region["id"] == "bright":
            state.set_brightness(value)
        else:
            state.set_volume(value)
        GLib.timeout_add(200, self.refresh)

    def on_scroll(self, x, y, direction):
        for region in self._regions:
            if region["kind"] != "slider":
                continue
            if not (region["x"] <= x <= region["x"] + region["w"]
                    and region["y"] <= y <= region["y"] + region["h"]):
                continue
            step = 5 if direction == 0 else -5
            if region["id"] == "bright":
                state.set_brightness(max(0, min(100, state.brightness() + step)))
            else:
                state.set_volume(max(0, min(100, state.volume() + step)))
            GLib.timeout_add(200, self.refresh)
            return True
        return False
