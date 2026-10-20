"""macOS-style dropdown menu panel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from ..macui import draw, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402


class Dropdown(Panel):
    """A floating menu, drawn as a glass sheet under the menu bar."""

    NAMESPACE = "mac-menu"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=False,
        )
        self.shell = shell
        self.items: list = []
        self.hover = -1
        self.title = ""
        self._geo: list = []

    # -- content -------------------------------------------------------------

    def open(self, title, items, x):
        self.title = title
        self.items = items
        self.hover = -1
        m = self.metrics
        w = int(m.px("menu_width"))
        h = int(m.px("menu_pad") * 2 + m.px("menu_item_h") * len(items))
        self.set_content_size(w, h)
        self.set_position(x, int(m.px("menu_bar_height")))
        self.show_all()
        self.redraw()

    def close(self):
        self.items = []
        self.hide()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        radius = m.px("menu_radius")
        draw.glass_panel(
            cr, 0, 0, width, height, radius, pal,
            exponent=m.squareness, shadow=True, shadow_spread=12,
        )
        pad = m.px("menu_pad")
        item_h = m.px("menu_item_h")
        self._geo = []
        for index, item in enumerate(self.items):
            y = pad + index * item_h
            if item.get("separator"):
                draw.fill_squircle(cr, 10, y + item_h / 2 - 0.5,
                                   width - 20, 1, 0.5, pal["separator"], 2.0)
                self._geo.append((y, item_h, item))
                continue
            label = item.get("label", "")
            if callable(item.get("label_fn")):
                label = item["label_fn"]()
            enabled = item.get("enabled", True)
            if index == self.hover and enabled:
                draw.fill_squircle(
                    cr, 4, y, width - 8, item_h, 6, pal["accent"], m.squareness
                )
            color = pal["on_accent"] if index == self.hover else (
                pal["text"] if enabled else pal["text_faint"]
            )
            weight = "bold" if index == self.hover else "normal"
            draw.draw_text(
                cr, 14, y + item_h / 2, label, m.font("menu_font_size"), color,
                weight=weight, baseline="middle",
            )
            shortcut = item.get("shortcut", "")
            if shortcut:
                draw.draw_text(
                    cr, width - 14, y + item_h / 2, shortcut,
                    m.font("menu_font_size"), pal["text_faint"], align="right",
                    baseline="middle",
                )
            self._geo.append((y, item_h, item))

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        index = -1
        for i, (iy, ih, _item) in enumerate(self._geo):
            if iy <= y <= iy + ih:
                index = i
                break
        if index != self.hover:
            self.hover = index
            self.redraw()
        return False

    def on_click(self, x, y, button):
        for iy, ih, item in self._geo:
            if iy <= y <= iy + ih:
                action = item.get("action")
                self.close()
                if action:
                    if callable(action):
                        action()
                    else:
                        self.shell.run_action(action)
                return True
        self.close()
        return True

    def on_leave(self):
        self.hover = -1
        self.redraw()
        return False
