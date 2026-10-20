"""The Spaces strip.

macOS puts a row of dots in the top right corner; the dot of the current
desktop is filled.  Clicking a dot switches to that desktop.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from ..macui import draw  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

DOT = 7
GAP = 9


class Spaces(Panel):
    NAMESPACE = "mac-spaces"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="top",
            anchors={"top": True, "right": True},
            margins={"top": int(metrics.px("menu_bar_height")) + 6, "right": 14},
        )
        self.shell = shell
        self._dots: list = []
        self._current = 1
        self.set_content_size(self.strip_width(),
                              int(metrics.px("menu_bar_height")))

    def strip_width(self):
        m = self.metrics
        count = 9
        return int((count * DOT + (count - 1) * GAP) * m.scale)

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._current = self.shell.current_tag()
        self.redraw()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        size = DOT * m.scale
        gap = GAP * m.scale
        count = 9
        total = count * size + (count - 1) * gap
        x = (width - total) / 2
        cy = height / 2

        self._dots = []
        for index in range(count):
            cx = x + index * (size + gap)
            active = index + 1 == self._current
            draw.fill_squircle(cr, cx, cy - size / 2, size, size, size / 2,
                               pal["text"] if active else pal["text_faint"], 2.0)
            self._dots.append((cx, cx + size, index + 1))

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        for left, right, tag in self._dots:
            if left <= x <= right:
                self.shell.switch_tag(tag)
                return True
        return False
