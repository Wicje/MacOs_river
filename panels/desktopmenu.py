"""The desktop itself, from the point of view of the pointer.

macOS answers a right click on the empty desktop with a small menu -- a
new folder on the desktop, the wallpaper, the appearance of the system
-- and a click on the empty space closes whatever panels are open.
This panel handles both: it sits in the lowest layer under the desktop
icons and the widget column, so a window that is there gets the click
first, and the empty desktop speaks to this one.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib  # noqa: E402

from ..macui.panel import Panel  # noqa: E402


class DesktopMenu(Panel):
    NAMESPACE = "mac-desktop"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="bottom",
            anchors={"top": True, "left": True, "right": True,
                     "bottom": True},
            keyboard=False,
        )
        self.shell = shell
        self._desktop_known = False
        self._resize()

    def _resize(self):
        width = self.metrics.width or 1366
        height = self.metrics.height or 768
        self.set_content_size(width, height)

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        # nothing to draw: the surface is the click receiver of the
        # empty desktop, and the wallpaper shows through

        self._resize()
        if not self._desktop_known:
            self._desktop_known = True

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        if button == 3:
            self.shell.open_desktop_menu()
            return True
        # a click on the empty desk dismisses whatever panels are open,
        # the way a click on the desktop of macOS closes them
        self.shell.desktop_clicked()
        return True