"""The Force Quit window list."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from ..macui import actions, draw  # noqa: E402
from ..macui.panel import Panel  # noqa: E402


class ForceQuit(Panel):
    NAMESPACE = "mac-force-quit"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=True,
        )
        self.shell = shell
        self._windows = []
        self._rows = []
        self.set_content_size(int(metrics.px("about_width")),
                              int(metrics.px("about_height")))
        self.refresh()

    def refresh(self):
        self._windows = actions.list_windows()
        self.redraw()

    def open(self):
        self.refresh()
        self.show_all()

    def close(self):
        self.hide()

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        draw.glass_panel(cr, 0, 0, width, height, m.px("about_radius"), pal,
                         exponent=m.squareness, shadow=True, shadow_spread=24)

        pad = m.px("about_pad")
        draw.draw_text(cr, width / 2, pad + 8, "Force Quit Applications",
                       m.px("about_font_large"), pal["text"], weight="bold",
                       align="center", baseline="middle")

        self._rows = []
        y = pad + 32
        row_h = 26
        for app_id, title in self._windows:
            if y + row_h > height - pad:
                break
            draw.draw_text(cr, pad, y + row_h / 2, title or app_id,
                           m.px("about_font"), pal["text"], baseline="middle",
                           max_width=width - pad * 2 - 60, ellipsize=True)
            draw.draw_text(cr, width - pad, y + row_h / 2, app_id,
                           m.px("about_font") * 0.9, pal["text_faint"],
                           align="right", baseline="middle")
            self._rows.append((y, row_h, title or app_id))
            y += row_h

        if not self._windows:
            draw.draw_text(cr, width / 2, height / 2, "No open applications",
                           m.px("about_font"), pal["text_faint"], align="center",
                           baseline="middle")

    def on_click(self, x, y, button):
        for ry, rh, title in self._rows:
            if ry <= y <= ry + rh:
                actions.kill_window(title)
                self.refresh()
                return True
        self.close()
        return True
