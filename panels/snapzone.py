"""The snap zone.

macOS Sequoia shows a translucent rectangle over the half of the screen a
window would take when it is dragged to the edge.  This panel draws that
rectangle: it follows the pointer to the left or the right edge of the
screen and disappears again when the pointer leaves.

The panel never takes the pointer, so it cannot swallow a click.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from ..macui import draw  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

MARGIN = 14


class SnapZone(Panel):
    NAMESPACE = "mac-snapzone"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True, "right": True, "bottom": True},
            keyboard=False,
        )
        self.shell = shell
        self.zone = ""
        self.set_content_size(-1, -1)

    # -- lifecycle -----------------------------------------------------------

    def show_zone(self, zone):
        """Show the rectangle of a zone, or nothing at all."""
        if zone == self.zone:
            return
        self.zone = zone
        if zone:
            self.show_all()
        else:
            self.hide()
        self.redraw()

    def close(self):
        self.zone = ""
        self.hide()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        if not self.zone:
            return
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        half = width / 2
        if self.zone == "left":
            x, w = MARGIN, half - MARGIN * 1.5
        else:
            x, w = half + MARGIN * 0.5, half - MARGIN * 1.5
        y = MARGIN
        h = height - MARGIN * 2

        # the body of the zone, the accent colour at a low opacity
        draw.fill_squircle(cr, x, y, w, h, 14 * scale,
                           (*pal["accent"][:3], 0.22), 2.0)
        draw.stroke_squircle(cr, x, y, w, h, 14 * scale,
                             (*pal["accent"][:3], 0.75), 2.0, 2.0)

        # the name of the zone
        label = "Tile left" if self.zone == "left" else "Tile right"
        draw.draw_text(cr, x + w / 2, y + h / 2, label,
                       16 * scale, pal["text"], weight="bold",
                       align="center", baseline="middle",
                       shadow=(0, 0, 0, 0.5))

    def input_rects(self):
        """The rectangle is only a picture: it takes no pointer at all."""
        return []
