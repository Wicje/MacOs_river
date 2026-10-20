"""The screenshot HUD.

macOS shows a small floating toolbar when the screenshot shortcut is
pressed, with the capture modes and the timer.  This panel does the same
and hands the choice to the screenshot script.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")

from ..macui import draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

SCRIPT = os.path.expanduser("~/.config/river/screenshot.sh")

BUTTONS = [
    ("region", "camera", "Capture area"),
    ("window", "display", "Capture window"),
    ("full", "display", "Capture screen"),
    ("timer5", "chevron_down", "Timer 5 seconds"),
    ("timer10", "chevron_down", "Timer 10 seconds"),
]


class ScreenshotHUD(Panel):
    NAMESPACE = "mac-screenshot-hud"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"bottom": True, "left": True, "right": True},
            margins={"bottom": int(metrics.px("dock_margin_bottom")) + 12},
            keyboard=False,
        )
        self.shell = shell
        self._buttons: list = []
        self.set_content_size(-1, 56)

    # -- lifecycle -----------------------------------------------------------

    def open(self):
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
        scale = m.scale

        size = 34 * scale
        gap = 10 * scale
        count = len(BUTTONS)
        total = count * (size + gap) - gap
        x = (width - total) / 2
        y = (height - size) / 2

        draw.fill_squircle(cr, x - 16 * scale, y - 10 * scale,
                           total + 32 * scale, size + 20 * scale, 16 * scale,
                           (*pal["menu_bar"][:3], 0.92), m.squareness)
        draw.stroke_squircle(cr, x - 16 * scale, y - 10 * scale,
                             total + 32 * scale, size + 20 * scale, 16 * scale,
                             pal["separator"], 1.0, m.squareness)

        self._buttons = []
        for index, (action, glyph, label) in enumerate(BUTTONS):
            bx = x + index * (size + gap)
            cr.save()
            cr.set_source_rgba(*pal["fill_hover"])
            cr.arc(bx + size / 2, y + size / 2, size / 2, 0, 2 * 3.14159)
            cr.fill()
            cr.restore()
            icon = 17 * scale
            fn = getattr(glyphs, glyph, None)
            if fn is not None:
                fn(cr, bx + (size - icon) / 2, y + (size - icon) / 2, icon,
                   pal["text"])
            self._buttons.append((action, bx, y, size, label))

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        return False

    def on_click(self, x, y, button):
        for action, bx, by, size, label in self._buttons:
            if bx <= x <= bx + size and by <= y <= by + size:
                self._run(action)
                self.close()
                return True
        self.close()
        return True

    def _run(self, action):
        if action.startswith("timer"):
            seconds = action.replace("timer", "")
            subprocess.Popen([SCRIPT, "region", "--delay", seconds],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        subprocess.Popen([SCRIPT, action], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
