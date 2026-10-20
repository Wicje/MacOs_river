"""Design metrics for the macOS Tahoe shell.

Every number in ``BASE`` is a macOS *point* measured against the reference
display (1366x768 at scale 1.0).  At runtime each value is multiplied by the
active scale factor so the shell keeps its proportions on a larger laptop
or on a HiDPI panel, exactly like macOS scales its own metrics.
"""

from __future__ import annotations

import json
import os
import subprocess

REFERENCE_WIDTH = 1366
REFERENCE_HEIGHT = 768

CONFIG_DIR = os.path.expanduser("~/.config/macshell")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# --- base points -----------------------------------------------------------

BASE = {
    # menu bar
    "menu_bar_height": 26,
    "menu_font_size": 13,
    "menu_item_gap": 10,
    "menu_pad_x": 12,
    "apple_logo": 14,
    "status_glyph": 15,
    "status_gap": 13,
    "clock_font_size": 13,
    # dock
    "dock_icon": 46,
    "dock_icon_max": 72,
    "dock_gap": 6,
    "dock_pad_x": 10,
    "dock_pad_y": 8,
    "dock_radius": 18,
    "dock_margin_bottom": 8,
    "dock_running_dot": 4,
    "dock_running_gap": 3,
    # control centre
    "cc_font_size": 11,
    "cc_font_size_bold": 12,
    "cc_font_size_title": 15,
    "cc_width": 238,
    "cc_radius": 22,
    "cc_pad": 12,
    "cc_gap": 10,
    "cc_col_gap": 10,
    "cc_pill_h": 46,
    "cc_circle": 44,
    "cc_small_circle": 32,
    "cc_tile_radius": 22,
    "cc_button": 32,
    "cc_button_gap": 10,
    "cc_slider_h": 22,
    "cc_slider_radius": 11,
    "cc_media_h": 88,
    "cc_section_gap": 12,
    # widgets column
    "widget_width": 216,
    "widget_size": 103,
    "widget_radius": 20,
    "widget_pad": 10,
    "widget_gap": 10,
    # notch
    "notch_width": 520,
    "notch_height": 64,
    "notch_radius": 14,
    "notch_pad": 16,
    "notch_art": 44,
    "notch_font_size": 12,
    # dropdown menus
    "menu_width": 210,
    "menu_item_h": 22,
    "menu_radius": 10,
    "menu_pad": 5,
    "menu_font_size": 13,
    # about / force quit sheets
    "about_width": 300,
    "about_height": 320,
    "about_radius": 20,
    "about_logo": 48,
    "about_pad": 20,
    "about_font": 12,
    "about_font_large": 16,
}

# --- colour tokens (overridable from config.json) ---------------------------

PALETTE = {
    "dark": {
        # the dark glass of macOS: the panels stay readable whatever the
        # wallpaper does, white text on a dark body
        "glass_top": [0.09, 0.09, 0.11, 0.62],
        "glass_bottom": [0.05, 0.05, 0.07, 0.52],
        "glass_edge_top": [1.0, 1.0, 1.0, 0.20],
        "glass_edge_bottom": [1.0, 1.0, 1.0, 0.05],
        "shadow": [0.0, 0.0, 0.0, 0.30],
        "text": [1.0, 1.0, 1.0, 1.0],
        "text_dim": [1.0, 1.0, 1.0, 0.62],
        "text_faint": [1.0, 1.0, 1.0, 0.38],
        "accent": [0.039, 0.518, 1.0, 1.0],
        "accent_dim": [0.039, 0.518, 1.0, 0.32],
        "fill": [1.0, 1.0, 1.0, 0.10],
        "fill_hover": [1.0, 1.0, 1.0, 0.18],
        "separator": [1.0, 1.0, 1.0, 0.10],
        "menu_bar": [0.055, 0.055, 0.075, 0.62],
        "switch_off": [0.55, 0.55, 0.60, 0.45],
        "on_accent": [1.0, 1.0, 1.0, 1.0],
    },
    "light": {
        "glass_top": [1.0, 1.0, 1.0, 0.55],
        "glass_bottom": [1.0, 1.0, 1.0, 0.36],
        "glass_edge_top": [1.0, 1.0, 1.0, 0.85],
        "glass_edge_bottom": [1.0, 1.0, 1.0, 0.45],
        "shadow": [0.0, 0.0, 0.0, 0.22],
        "text": [0.0, 0.0, 0.0, 1.0],
        "text_dim": [0.0, 0.0, 0.0, 0.62],
        "text_faint": [0.0, 0.0, 0.0, 0.38],
        "accent": [0.0, 0.478, 1.0, 1.0],
        "accent_dim": [0.0, 0.478, 1.0, 0.28],
        "fill": [0.0, 0.0, 0.0, 0.06],
        "fill_hover": [0.0, 0.0, 0.0, 0.12],
        "separator": [0.0, 0.0, 0.0, 0.10],
        "menu_bar": [1.0, 1.0, 1.0, 0.34],
        "switch_off": [0.35, 0.35, 0.38, 0.35],
        "on_accent": [1.0, 1.0, 1.0, 1.0],
    },
}

ACCENTS = {
    "blue": (0.039, 0.518, 1.0),
    "purple": (0.62, 0.32, 0.94),
    "pink": (0.98, 0.36, 0.62),
    "red": (1.0, 0.23, 0.19),
    "orange": (1.0, 0.58, 0.16),
    "yellow": (1.0, 0.80, 0.10),
    "green": (0.30, 0.80, 0.35),
    "graphite": (0.55, 0.55, 0.58),
}

DEFAULTS = {
    "scale_mode": "auto",      # auto | output | manual
    "scale": 1.0,              # used when scale_mode == manual
    "theme": "dark",           # dark | light
    "squareness": 5.0,         # superellipse exponent for continuous corners
    "show_widgets": True,
    "show_dock": True,
    "show_notch": True,
    "accent": "blue",
    "reduce_transparency": False,
    "wallpaper_rotate": True,
    "show_desktop_icons": True,
    # always | desktop | auto: the dock stays on the desktop, steps aside
    # for an application and comes back at the edge of the screen
    "dock_mode": "desktop",
    # always | auto: the notch waits for the pointer at the top edge
    "notch_mode": "auto",
    # the Liquid Glass controls: how opaque the panels are (0.5 … 1.5) and
    # how much accent colour they carry (0 … 1)
    "glass_opacity": 1.0,
    "glass_tint": 0.0,
}


def _run_json(cmd):
    try:
        out = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=3
        ).stdout.strip()
        return json.loads(out) if out else None
    except Exception:
        return None


def detect_output():
    """Return (width, height, scale) for the primary output.

    Sway/SwayFX first, then River, then a sane fallback so the shell still
    renders when the compositor cannot be queried.
    """
    data = _run_json("swaymsg -r get_outputs")
    if isinstance(data, list):
        for out in data:
            if out.get("active") and not out.get("disabled"):
                rect = out.get("rect") or {}
                scale = out.get("scale") or 1
                return int(rect.get("width", 0)), int(rect.get("height", 0)), float(scale)
        if data:
            rect = data[0].get("rect") or {}
            return int(rect.get("width", 0)), int(rect.get("height", 0)), 1.0

    data = _run_json("riverctl get-outputs")
    if isinstance(data, list):
        for out in data:
            if out.get("active"):
                mode = (out.get("current_mode") or {}).get("width", 0)
                return int(mode), 0, 1.0
        if data:
            mode = (data[0].get("current_mode") or {}).get("width", 0)
            return int(mode), 0, 1.0

    # wlr-randr works on every wlroots compositor, including River.
    try:
        out = subprocess.run(
            "wlr-randr", shell=True, capture_output=True, text=True, timeout=3
        ).stdout
    except Exception:
        out = ""
    if out:
        current = False
        width = height = 0
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Current mode:"):
                current = True
            elif current and "px" in line:
                parts = line.split()
                try:
                    width = int(parts[0])
                    height = int(parts[2])
                except (ValueError, IndexError):
                    pass
                break
        if width:
            return width, height, 1.0

    return REFERENCE_WIDTH, REFERENCE_HEIGHT, 1.0


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return cfg


class Metrics:
    """Scales the base point values to the current output."""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.width, self.height, self.output_scale = detect_output()
        self.scale = self._resolve_scale()

    def reload(self):
        """Re-read config.json.

        Returns True when something that affects the drawing changed, so the
        caller can repaint.  The shell calls this once a second, which is
        what makes the light/dark switch instant.
        """
        before = (self.config.get("theme"), self.config.get("scale_mode"),
                  self.config.get("scale"), self.config.get("squareness"))
        self.config = load_config()
        after = (self.config.get("theme"), self.config.get("scale_mode"),
                 self.config.get("scale"), self.config.get("squareness"))
        return before != after

    def _resolve_scale(self):
        mode = self.config.get("scale_mode", "auto")
        if mode == "manual":
            return float(self.config.get("scale", 1.0))
        if mode == "output":
            return float(self.output_scale or 1.0)
        # auto: honour fractional scaling, otherwise grow gently with the
        # panel so a bigger laptop keeps the same visual density.
        if self.output_scale and self.output_scale > 1.0:
            return float(self.output_scale)
        if self.width:
            ratio = self.width / REFERENCE_WIDTH
            return max(1.0, min(ratio, 1.6))
        return 1.0

    def px(self, name):
        """Scaled pixel value for a base metric name."""
        return BASE[name] * self.scale

    def raw(self, name):
        return BASE[name]

    def font(self, name, size_name=None):
        """Font size in scaled points."""
        return self.px(size_name or name)

    @property
    def squareness(self):
        return float(self.config.get("squareness", 5.0))

    def palette(self, theme=None):
        palette = dict(PALETTE[theme or self.config.get("theme", "dark")])
        accent = ACCENTS.get(self.config.get("accent", "blue"))
        if accent:
            palette["accent"] = (*accent, 1.0)
            palette["accent_dim"] = (*accent, palette["accent_dim"][3])
        # the Liquid Glass controls of macOS: how opaque the panels are and
        # how much of the accent colour they carry
        opacity = float(self.config.get("glass_opacity", 1.0))
        tint = float(self.config.get("glass_tint", 0.0))
        if opacity != 1.0 or tint:
            for key in ("glass_top", "glass_bottom"):
                r, g, b, a = palette[key]
                a = max(0.0, min(1.0, a * opacity))
                if tint and accent:
                    r += (accent[0] - r) * tint
                    g += (accent[1] - g) * tint
                    b += (accent[2] - b) * tint
                palette[key] = (r, g, b, a)
        if self.config.get("reduce_transparency"):
            palette["glass_top"] = (0.09, 0.09, 0.11, 0.95)
            palette["glass_bottom"] = (0.06, 0.06, 0.08, 0.92)
            palette["menu_bar"] = (0.055, 0.055, 0.075, 0.95)
        return palette

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as fh:
            json.dump(self.config, fh, indent=4)
