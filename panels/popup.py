"""Menu bar popups.

Clicking the Wi-Fi, Bluetooth, battery or sound icon in the menu bar opens
a small flyout underneath it, the way macOS does.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui import draw, glyphs, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

WIDTH = 260
ROW_HEIGHT = 30
TITLE_HEIGHT = 30


def _run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=4).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class StatusPopup(Panel):
    """A flyout with a title and a list of rows."""

    NAMESPACE = "mac-status-popup"

    def __init__(self, metrics, shell, kind):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=False,
        )
        self.shell = shell
        self.kind = kind
        self._rows: list = []
        self._title = ""
        self.set_content_size(int(metrics.px("menu_width") * 1.25), 200)

    # -- lifecycle -----------------------------------------------------------

    def open(self, anchor_x=None):
        self._title, self._rows = self._collect()
        self.show_items(self._title, self._rows, anchor_x)

    def show_items(self, title, rows, anchor_x=None, anchor_y=None):
        """Show a list of rows, optionally under a menu bar item."""
        self._title = title
        self._rows = rows
        width = int(self.metrics.px("menu_width") * 1.25)
        height = int(TITLE_HEIGHT * self.metrics.scale
                     + len(rows) * ROW_HEIGHT * self.metrics.scale + 20)
        self.set_content_size(width, height)
        if anchor_x is None:
            anchor_x = (self.metrics.width or 1366) - width - 8
        else:
            anchor_x = anchor_x - width + 20
        if anchor_y is None:
            anchor_y = int(self.metrics.px("menu_bar_height")) + 4
        self.set_position(int(max(4, anchor_x)), int(anchor_y))
        self.show_all()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self, anchor_x=None):
        if self.get_visible():
            self.close()
        else:
            self.open(anchor_x)

    # -- data ----------------------------------------------------------------

    def _collect(self):
        if self.kind == "wifi":
            return self._wifi()
        if self.kind == "bluetooth":
            return self._bluetooth()
        if self.kind == "battery":
            return self._battery()
        return self._volume()

    def _wifi(self):
        rows = []
        # what the meter says, before the networks of the air
        try:
            from ..macui import traffic
            m_rx, m_tx = traffic.month_total()
            d_rx, d_tx = traffic.day_total()
            rows.append({
                "glyph": "grid",
                "label": f"This month  ↓ {traffic.human(m_rx)}   "
                         f"↑ {traffic.human(m_tx)}",
                "detail": "", "active": False, "action": None,
            })
            rows.append({
                "glyph": "grid",
                "label": f"Today  ↓ {traffic.human(d_rx)}   "
                         f"↑ {traffic.human(d_tx)}",
                "detail": "", "active": False, "action": None,
            })
        except Exception:  # noqa: BLE001 — the meter may not be running
            pass
        out = _run("nmcli -t -f ACTIVE,SSID,SIGNAL device wifi")
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 3 or not parts[1]:
                continue
            active = parts[0] == "yes"
            ssid = parts[1]
            try:
                signal = int(parts[2])
            except ValueError:
                signal = 0
            rows.append({
                "glyph": "wifi",
                "label": ssid,
                "detail": f"{signal}%",
                "active": active,
                "action": (lambda name=ssid: state.spawn(
                    f"nmcli device wifi connect '{name}'")) if not active else None,
            })
        if not rows:
            rows.append({"glyph": "wifi", "label": "No networks found",
                         "detail": "", "active": False, "action": None})
        rows.append({"glyph": "grid", "label": "Wi-Fi Settings…", "detail": "",
                     "active": False, "action": self.shell.open_settings})
        return "Wi-Fi", rows

    def _bluetooth(self):
        rows = []
        out = _run("bluetoothctl devices")
        for line in out.splitlines():
            if not line.startswith("Device"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[-1]
            rows.append({"glyph": "bluetooth", "label": name, "detail": "",
                         "active": False, "action": None})
        if not rows:
            rows.append({"glyph": "bluetooth", "label": "No devices",
                         "detail": "", "active": False, "action": None})
        rows.append({"glyph": "grid", "label": "Bluetooth Settings…",
                     "detail": "", "active": False,
                     "action": self.shell.open_settings})
        return "Bluetooth", rows

    def _battery(self):
        rows = []
        level = None
        charging = False
        for name in ("BAT0", "BAT1"):
            path = f"/sys/class/power_supply/{name}/capacity"
            try:
                with open(path) as fh:
                    level = int(fh.read().strip())
                break
            except (OSError, ValueError):
                continue
        try:
            with open("/sys/class/power_supply/BAT0/status") as fh:
                charging = "Charging" in fh.read()
        except OSError:
            pass
        if level is not None:
            rows.append({"glyph": "battery", "label": f"{level}%",
                         "detail": "Charging" if charging else "On battery",
                         "active": charging, "action": None})
        rows.append({"glyph": "grid", "label": "Battery Settings…", "detail": "",
                     "active": False, "action": self.shell.open_settings})
        return "Battery", rows

    def _volume(self):
        rows = []
        out = _run("wpctl status")
        sink = ""
        for line in out.splitlines():
            if "Sink:" in line:
                sink = line.split(":", 1)[1].strip()
                break
        volume = state.volume()
        rows.append({"glyph": "speaker", "label": sink or "Audio Output",
                     "detail": f"{volume}%", "active": volume > 0,
                     "action": None})
        rows.append({"glyph": "grid", "label": "Sound Settings…", "detail": "",
                     "active": False, "action": self.shell.open_settings})
        return "Sound", rows

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        row_h = ROW_HEIGHT * m.scale
        title_h = TITLE_HEIGHT * m.scale

        draw.glass_panel(cr, 0, 0, width, height, 14 * m.scale, pal,
                         exponent=m.squareness, shadow=True, shadow_spread=16)

        draw.draw_text(cr, 14 * m.scale, title_h * 0.55, self._title,
                       m.font("cc_font_size_bold"), pal["text"], weight="bold",
                       baseline="middle")

        self._geo = []
        y = title_h
        for row in self._rows:
            glyph = 15 * m.scale
            color = pal["text"] if row.get("active") else pal["text_dim"]
            self._draw_glyph(cr, row.get("glyph", "grid"),
                             14 * m.scale, y + (row_h - glyph) / 2, glyph, color)
            draw.draw_text(cr, 38 * m.scale, y + row_h / 2, row["label"],
                           m.font("cc_font_size"), pal["text"], baseline="middle",
                           max_width=width - 90 * m.scale, ellipsize=True)
            if row.get("detail"):
                draw.draw_text(cr, width - 14 * m.scale, y + row_h / 2,
                               row["detail"], m.font("cc_font_size"),
                               pal["text_faint"], align="right", baseline="middle")
            self._geo.append((y, row_h, row))
            y += row_h

    def _draw_glyph(self, cr, name, x, y, size, color):
        fn = getattr(glyphs, name, None)
        if fn is None:
            return
        fn(cr, x, y, size, color)

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        for ry, rh, row in getattr(self, "_geo", []):
            if ry <= y <= ry + rh:
                action = row.get("action")
                if action:
                    action()
                self.close()
                return True
        self.close()
        return True
