"""Pointer sensors.

A thin invisible strip along the edge of the screen.  The pointer events
it receives tell the shell where the mouse is, which is what the auto
hiding dock and notch need: the panel only appears when the pointer
reaches the edge of the screen.

The strips on the left and the right tell the shell that a window could
be snapped there, which is what the snap zone of macOS Sequoia shows.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from ..macui.panel import Panel  # noqa: E402

STRIP = 4

ANCHORS = {
    "top": {"top": True, "left": True, "right": True},
    "bottom": {"bottom": True, "left": True, "right": True},
    "left": {"top": True, "left": True, "bottom": True},
    "right": {"top": True, "right": True, "bottom": True},
}


class Sensor(Panel):
    NAMESPACE = "mac-sensor"

    def __init__(self, metrics, shell, edge="top"):
        super().__init__(
            metrics,
            # the top strip lies above the menu bar, so it is on the
            # overlay layer; both strips are mapped after the panels, so
            # they always get the pointer
            layer="overlay" if edge == "top" else "top",
            anchors=ANCHORS.get(edge, ANCHORS["top"]),
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
        screen_w = self.metrics.width or 1366
        if self.edge == "top":
            absolute = y
        elif self.edge == "bottom":
            absolute = screen_h - STRIP + y
        elif self.edge == "left":
            absolute = x
        else:
            absolute = screen_w - STRIP + x
        self.shell.pointer_moved(self.edge, absolute)
        return False

    def on_leave(self):
        """The pointer left the strip, so the panel goes away again."""
        self.shell.pointer_left(self.edge)
        return False

    def on_click(self, x, y, button):
        """A click on the edge snaps the window to that side."""
        if self.edge in ("left", "right"):
            self.shell.snap_window(self.edge)
            return True
        return False
