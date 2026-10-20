"""The "About This Mac" panel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from ..macui import actions, draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402


class About(Panel):
    NAMESPACE = "mac-about"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=True,
        )
        self.shell = shell
        self.set_content_size(int(metrics.px("about_width")),
                              int(metrics.px("about_height")))

    def open(self):
        self.show_all()
        self.redraw()

    def close(self):
        self.hide()

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        draw.glass_panel(cr, 0, 0, width, height, m.px("about_radius"), pal,
                         exponent=m.squareness, shadow=True, shadow_spread=24)

        info = actions.system_info()
        cx = width / 2

        logo = m.px("about_logo")
        glyphs.apple(cr, cx - logo / 2, m.px("about_pad"), logo, pal["text"])

        title_y = m.px("about_pad") + logo + 16
        draw.draw_text(cr, cx, title_y, info["shell"], m.px("about_font_large"),
                       pal["text"], weight="bold", align="center", baseline="middle")
        draw.draw_text(cr, cx, title_y + 20, f"{info['os']} · {info['compositor']}",
                       m.px("about_font"), pal["text_dim"], align="center",
                       baseline="middle")

        rows = [
            ("Chip", info["cpu"] or "Unknown"),
            ("Graphics", info["gpu"] or "Unknown"),
            ("Memory", info["memory"] or "Unknown"),
            ("Disk", info["disk"] or "Unknown"),
            ("Display", info["display"] or "Unknown"),
            ("Kernel", info["kernel"]),
            ("Uptime", info["uptime"] or "Unknown"),
        ]
        y = title_y + 40
        for label, value in rows:
            draw.draw_text(cr, m.px("about_pad"), y, label, m.px("about_font"),
                           pal["text_faint"], baseline="middle")
            draw.draw_text(cr, width - m.px("about_pad"), y, value,
                           m.px("about_font"), pal["text"], align="right",
                           baseline="middle", max_width=width * 0.62,
                           ellipsize=True)
            y += 21

        draw.draw_text(cr, cx, height - m.px("about_pad"),
                       "Close", m.px("about_font"), pal["text_dim"],
                       align="center", baseline="middle")

    def on_click(self, x, y, button):
        self.close()
        return True

    def on_key(self, widget, event):
        return False
