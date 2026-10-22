"""Launchpad.

The macOS application grid: a dimmed desktop with the installed
applications laid out in rows of icons, and a search field at the top.
"""

from __future__ import annotations

import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

ENTRY_CSS = b"""
entry {
    background: transparent;
    border: none;
    color: #ffffff;
    font-family: "SF Pro Text";
    font-size: 16px;
    caret-color: #ffffff;
    padding: 0;
}
entry:focus { box-shadow: none; outline: none; }
"""

ICON_SIZE = 64
LABEL_SIZE = 11
COLUMNS = 7
PADDING = 18


class Launchpad(Panel):
    NAMESPACE = "mac-launchpad"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True, "right": True, "bottom": True},
            keyboard=True,
        )
        self.shell = shell
        self._results: list = []
        self._icons: list = []
        self._cells: list = []
        self.hover = -1
        self.show_everything = False

        provider = Gtk.CssProvider()
        provider.load_from_data(ENTRY_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.entry = Gtk.Entry()
        self.entry.set_has_frame(False)
        self.entry.set_can_focus(True)
        self.entry.set_placeholder_text("Search")
        self.entry.connect("activate", self._on_activate)
        self.entry.connect("changed", self._on_changed)
        self.entry.connect("key-press-event", self._on_key)

        overlay = Gtk.Overlay()
        self.remove(self.area)
        overlay.add(self.area)
        overlay.add_overlay(self.entry)
        self.add(overlay)

    # -- lifecycle -----------------------------------------------------------

    def open(self):
        self._results = apps.search("", show_all=self.show_everything)
        self.entry.set_text("")
        self.show_all()
        self.entry.grab_focus()
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self):
        if self.get_visible():
            self.close()
        else:
            self.open()

    # -- search --------------------------------------------------------------

    def _on_changed(self, entry):
        text = entry.get_text().strip()
        self._results = apps.search(text, show_all=bool(text) or self.show_everything)
        self.redraw()

    def _on_activate(self, entry):
        if self._results:
            self._launch(self._results[0])

    def _launch(self, app):
        subprocess.Popen(app["exec"], shell=True, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()

        # dimmed desktop behind the grid
        cr.set_source_rgba(0.02, 0.02, 0.03, 0.55)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        icon = int(ICON_SIZE * m.scale)
        label = LABEL_SIZE * m.scale
        pad = PADDING * m.scale
        cols = COLUMNS

        # the grid is scaled down until it fits on the screen
        top = 92 * m.scale
        available = max(height - top - 16 * m.scale, 120 * m.scale)
        rows = max(1, (len(self._results) + cols - 1) // cols)
        cell_h = available / rows
        if cell_h < icon + label + pad:
            icon = int(max(28 * m.scale, cell_h - label - pad * 1.4))
            cell_h = icon + label + pad * 1.4

        cell_w = icon + pad

        grid_h = rows * cell_h
        top = max(top, (height - grid_h) / 2 + 30 * m.scale)
        left = (width - cols * cell_w) / 2

        self._cells = []
        for index, app in enumerate(self._results):
            col = index % cols
            row = index // cols
            x = left + col * cell_w
            y = top + row * cell_h
            self._cells.append((x, y, icon, app))

            pixbuf = self._icon_for(app)
            if pixbuf is not None:
                iw, ih = pixbuf.get_width(), pixbuf.get_height()
                scale = icon / max(iw, ih)
                cr.save()
                cr.translate(x + (icon - iw * scale) / 2, y + (icon - ih * scale) / 2)
                cr.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
            else:
                draw.fill_squircle(cr, x, y, icon, icon, icon * 0.22,
                                   pal["fill_hover"], m.squareness)
                glyphs.grid(cr, x + icon * 0.26, y + icon * 0.26, icon * 0.48,
                            pal["text"])

            draw.draw_text(cr, x + icon / 2, y + icon + label * 0.9, app["name"],
                           label, pal["text"], align="center", baseline="middle",
                           max_width=cell_w - 4, ellipsize=True)

        # the button that switches between the grid and the full list
        button_w = 96 * m.scale
        button_h = 26 * m.scale
        button_x = (width - button_w) / 2
        button_y = height - button_h - 18 * m.scale
        draw.fill_squircle(cr, button_x, button_y, button_w, button_h,
                           button_h / 2, pal["fill_hover"], 2.0)
        draw.draw_text(cr, button_x + button_w / 2, button_y + button_h / 2,
                       "Show All" if not self.show_everything else "Show Fewer",
                       m.font("cc_font_size"), pal["text"], align="center",
                       baseline="middle")
        self._toggle = (button_x, button_y, button_w, button_h)

        # the search field
        field_w = 280 * m.scale
        field_h = 34 * m.scale
        field_x = (width - field_w) / 2
        field_y = 44 * m.scale
        draw.fill_squircle(cr, field_x, field_y, field_w, field_h,
                           field_h / 2, pal["fill_hover"], 2.0)
        glyph = 16 * m.scale
        glyphs.spotlight(cr, field_x + 16 * m.scale, field_y + (field_h - glyph) / 2,
                         glyph, pal["text_dim"])

        self.entry.set_size_request(int(field_w - 60 * m.scale),
                                    int(field_h * 0.6))
        self.entry.set_halign(Gtk.Align.START)
        self.entry.set_valign(Gtk.Align.CENTER)
        self.entry.set_margin_start(int(field_x + 40 * m.scale))

    def _icon_for(self, app):
        path = app.get("icon_path")
        if path is None:
            # the icons the shell ships come first, so the grid keeps the
            # look of the dock; the rest takes the icon of the desktop
            command = (app.get("exec") or "").split()
            bundled = apps.bundled_icon_for(app.get("id"),
                                            command[0] if command else "")
            path = draw.bundled_icon_path(bundled) if bundled else None
            if not path:
                path = apps.icon_path(app.get("icon") or "")
            app["icon_path"] = path
        if not path:
            return None
        return draw.load_icon(path)

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        found = -1
        for index, (cx, cy, size, _app) in enumerate(self._cells):
            if cx <= x <= cx + size and cy <= y <= cy + size:
                found = index
                break
        if found != self.hover:
            self.hover = found
            self.redraw()
        return False

    def _on_key(self, widget, event):
        """Escape closes the panel."""
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def on_click(self, x, y, button):
        if hasattr(self, "_toggle"):
            bx, by, bw, bh = self._toggle
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.show_everything = not self.show_everything
                self._results = apps.search(self.entry.get_text().strip(),
                                           show_all=self.show_everything)
                self.redraw()
                return True
        for cx, cy, size, app in self._cells:
            if cx <= x <= cx + size and cy <= y <= cy + size:
                if button == 3:
                    # the right button opens the menu of the application
                    self.shell.open_app_menu(app)
                    return True
                self._launch(app)
                return True
        return False

    def on_key(self, widget, event):
        return False
