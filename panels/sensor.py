"""Pointer sensors.

A thin invisible strip along the top or the bottom of the screen.  The
pointer events it receives tell the shell where the mouse is, which is
what the auto hiding dock and notch need: the panel only appears when the
pointer reaches the edge of the screen.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from ..macui.panel import Panel  # noqa: E402

STRIP = 4


class Sensor(Panel):
    NAMESPACE = "mac-sensor"

    def __init__(self, metrics, shell, edge="top"):
        anchors = ({"top": True, "left": True, "right": True}
                   if edge == "top" else
                   {"bottom": True, "left": True, "right": True})
        super().__init__(
            metrics,
            # the top strip lies above the menu bar, so it is on the
            # overlay layer; both strips are mapped after the panels, so
            # they always get the pointer
            layer="overlay" if edge == "top" else "top",
            anchors=anchors,
            margins={"left": 0, "right": 0},
            keyboard=False,
        )
        self.shell = shell
        self.edge = edge
        self.set_content_size(-1, STRIP)

    def paint(self, cr, width, height):
        """Nothing to see: the strip is only an event surface."""
        return

    def on_motion(self, x, y):
        screen_h = self.metrics.height or 768
        absolute = y if self.edge == "top" else screen_h - STRIP + y
        self.shell.pointer_moved(self.edge, absolute)
        return False

    def on_leave(self):
        """The pointer left the strip, so the panel goes away again."""
        self.shell.pointer_left(self.edge)
        return False
