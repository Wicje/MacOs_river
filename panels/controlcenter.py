"""The macOS Tahoe Control Centre.

Tahoe turned the Control Centre into a narrow, tall panel of glass pills
and circles: connectivity on the left, media and utilities on the right.
This module reproduces that arrangement.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
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

        # -- left column --------------------------------------------------
        y = pad
        regions.append({
            "kind": "pill", "id": "wifi", "glyph": "wifi", "label": "Wi-Fi",
            "x": left_x, "y": y, "w": col_w, "h": m.px("cc_pill_h"),
        })
        y += m.px("cc_pill_h") + gap

        regions.append({
            "kind": "circle", "id": "bluetooth", "glyph": "bluetooth",
            "label": "Bluetooth",
            "x": left_x, "y": y, "w": m.px("cc_circle"), "h": m.px("cc_circle"),
        })
        y += m.px("cc_circle") + gap

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
        y = pad
        regions.append({
            "kind": "media", "x": right_x, "y": y, "w": col_w,
            "h": m.px("cc_media_h"),
        })
        y += m.px("cc_media_h") + gap

        for tile in ({"id": "airplay", "glyph": "airplay"},
                     {"id": "display", "glyph": "display"}):
            regions.append({
                "kind": "circle", "id": tile["id"], "glyph": tile["glyph"],
                "label": tile["id"],
                "x": right_x, "y": y, "w": m.px("cc_circle"),
                "h": m.px("cc_circle"),
            })
            right_x += m.px("cc_circle") + gap
        right_x = self._columns(width)[2]
        y += m.px("cc_circle") + m.px("cc_section_gap")

        utilities = [
            ("accessibility", "accessibility"),
            ("appearance", "moon"),
            ("launchpad", "grid"),
            ("spotlight", "spotlight"),
            ("mirror", "airplay"),
            ("sound", "speaker"),
            ("control", "control_center"),
            ("display", "display"),
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

        regions.append({
            "kind": "exit", "x": right_x, "y": y, "w": col_w, "h": 26,
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
        art = 34 * m.scale
        x, y = region["x"], region["y"]
        w = region["w"]
        media = self._media

        art_x = x + (w - art) / 2
        draw.fill_squircle(cr, art_x, y + 8 * m.scale, art, art, art * 0.18,
                           pal["fill"], m.squareness)
        if media:
            draw.draw_text(cr, art_x + art / 2, y + 8 * m.scale + art / 2,
                           (media[0] or "?")[0].upper(), art * 0.5, pal["text"],
                           weight="bold", align="center", baseline="middle")
        else:
            glyphs.speaker(cr, art_x + art * 0.28, y + 8 * m.scale + art * 0.28,
                           art * 0.44, pal["text_dim"])

        title = media[0] if media else "Not Playing"
        artist = media[1] if media else "—"
        draw.draw_text(cr, x + w / 2, y + art + 26 * m.scale, title,
                       m.font("cc_font_size_bold"), pal["text"], weight="bold",
                       align="center", max_width=w - 8 * m.scale, ellipsize=True)
        draw.draw_text(cr, x + w / 2, y + art + 42 * m.scale, artist or "—",
                       m.font("cc_font_size"), pal["text_dim"], align="center",
                       max_width=w - 8 * m.scale, ellipsize=True)

    def _paint_exit(self, cr, region, pal):
        m = self.metrics
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        draw.fill_squircle(cr, x, y, w, h, h / 2, pal["fill_hover"], 2.0)
        draw.draw_text(cr, x + w / 2, y + h / 2, "Exit Controls",
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
            if kind == "pill":
                self._activate(region["id"])
            elif kind == "circle":
                self._activate(region["id"])
            elif kind == "slider":
                self._set_slider(region, x)
            elif kind == "exit":
                self.hide()
            return True
        return False

    def _activate(self, region_id):
        if region_id == "wifi":
            state.toggle_wifi()
        elif region_id == "bluetooth":
            state.toggle_bluetooth()
        elif region_id == "focus":
            state.toggle_dnd()
        elif region_id == "appearance":
            state.toggle_theme()
        elif region_id == "launchpad":
            state.spawn("wofi --show drun")
        elif region_id == "spotlight":
            self.shell.open_spotlight()
        elif region_id == "sound":
            state.toggle_mute()
        elif region_id == "control":
            self.hide()
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
