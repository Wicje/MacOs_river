"""Spotlight-style search overlay.

A glass search card under the menu bar.  Typing filters the installed
applications and the folders in the home directory; clicking a result (or
pressing return) launches it.
"""

from __future__ import annotations

import ast
import operator
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs  # noqa: E402
from ..macui import panel as panel_module  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

MAX_RESULTS = 7


class Spotlight(Panel):
    NAMESPACE = "mac-spotlight"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True, "right": True},
            margins={"top": 90},
            keyboard=True,
        )
        self.shell = shell
        self._results: list = []
        self.hover = -1
        self.set_content_size(-1, self.card_height())

        provider = Gtk.CssProvider()
        provider.load_from_data(panel_module.entry_css(
            metrics.config.get("theme", "dark")))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.entry = Gtk.Entry()
        self.entry.set_has_frame(False)
        self.entry.set_can_focus(True)
        self.entry.set_placeholder_text("Spotlight Search")
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
        self.entry.set_text("")
        self._results = []
        self.set_content_size(-1, self.card_height())
        self.show_all()
        self.entry.grab_focus()
        self.redraw()

    def close(self):
        self.hide()

    # -- geometry ------------------------------------------------------------

    def card_width(self, width):
        m = self.metrics
        return min(width - 240 * m.scale, 640 * m.scale)

    def field_height(self):
        return 56 * self.metrics.scale

    def card_height(self):
        rows = len(self._results)
        extra = 0
        entry = getattr(self, "entry", None)
        if self._results or (entry is not None and entry.get_text().strip()):
            # the row that asks the assistant
            extra = 30 * self.metrics.scale
        return self.field_height() + rows * 30 * self.metrics.scale + extra

    def _card_rect(self, width):
        m = self.metrics
        w = self.card_width(width)
        x = (width - w) / 2
        return x, 0, w, self.card_height()

    # -- search --------------------------------------------------------------

    def _search(self, text):
        if not text:
            return []
        needle = text.lower()
        results = []
        for entry in apps.all_applications():
            label = entry.get("name") or ""
            if needle in label.lower():
                results.append((label, entry.get("exec") or "", "app"))
        home = os.path.expanduser("~")
        try:
            for entry in sorted(os.listdir(home))[:400]:
                if needle in entry.lower():
                    results.append((entry, os.path.join(home, entry), "folder"))
        except OSError:
            pass
        results.sort(key=lambda item: (not item[0].lower().startswith(needle),
                                       len(item[0])))
        results = results[:MAX_RESULTS]
        results.append((f"Search the web for \u201c{text}\u201d", text, "web"))
        return results

    def _on_changed(self, entry):
        text = entry.get_text().strip()
        self._results = self._search(text)
        self.set_content_size(-1, self.card_height())
        self.redraw()

    def _launch(self, item):
        label, command, kind = item
        if kind == "calc":
            subprocess.Popen(["wl-copy"], input=command.encode(),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.close()
            return
        if kind == "web":
            import urllib.parse
            url = "https://duckduckgo.com/?q=" + urllib.parse.quote(command)
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.close()
            return
        if kind == "app":
            subprocess.Popen(command, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["dolphin", command], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    def _on_activate(self, entry):
        if self._results:
            self._launch(self._results[0])
        else:
            text = entry.get_text().strip()
            self.close()
            if text:
                subprocess.Popen(["wofi", "--show", "drun"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        x, y, w, h = self._card_rect(width)
        field_h = self.field_height()
        radius = field_h / 2 if not self._results else 22 * m.scale

        draw.glass_panel(cr, x, y, w, h, radius, pal,
                         exponent=m.squareness, shadow=True, shadow_spread=22)

        glyph = 20 * m.scale
        glyphs.spotlight(cr, x + 20 * m.scale, (field_h - glyph) / 2, glyph,
                         pal["text_dim"])

        row_h = 30 * m.scale
        if self._results:
            for index, (label, _command, kind) in enumerate(self._results):
                ry = field_h + index * row_h
                if self.hover == index:
                    draw.fill_squircle(cr, x + 6 * m.scale, ry + 2 * m.scale,
                                       w - 12 * m.scale, row_h - 4 * m.scale,
                                       8 * m.scale, pal["fill_hover"], 2.0)
                draw.draw_text(cr, x + 44 * m.scale, ry + row_h / 2, label,
                               m.font("menu_font_size"), pal["text"],
                               baseline="middle")
                caption = {"app": "Application", "folder": "Folder",
                           "calc": "Calculator", "web": "Web"}.get(kind, "")
                draw.draw_text(cr, x + w - 20 * m.scale, ry + row_h / 2,
                               caption, m.font("cc_font_size"), pal["text_faint"],
                               align="right", baseline="middle")

        # the row that hands the question to the assistant
        ask_y = field_h + len(self._results) * row_h
        if self._results or self.entry.get_text().strip():
            self._ask_row = (x + 6 * m.scale, ask_y, w - 12 * m.scale,
                             row_h - 4 * m.scale)
            if self.hover == len(self._results):
                draw.fill_squircle(cr, x + 6 * m.scale, ask_y + 2 * m.scale,
                                   w - 12 * m.scale, row_h - 4 * m.scale,
                                   8 * m.scale, pal["fill_hover"], 2.0)
            draw.draw_text(cr, x + 44 * m.scale, ask_y + row_h / 2,
                           "Ask the assistant", m.font("menu_font_size"),
                           pal["text_dim"], baseline="middle")
            draw.draw_text(cr, x + w - 20 * m.scale, ask_y + row_h / 2,
                           "Siri", m.font("cc_font_size"), pal["text_faint"],
                           align="right", baseline="middle")
        else:
            self._ask_row = None

        # keep the entry aligned with the search glyph
        self.entry.set_size_request(int(w - 110 * m.scale),
                                    int(field_h * 0.6))
        self.entry.set_halign(Gtk.Align.START)
        self.entry.set_valign(Gtk.Align.CENTER)
        self.entry.set_margin_start(int(x + 50 * m.scale))

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        field_h = self.field_height()
        row_h = 30 * self.metrics.scale
        index = -1
        if y >= field_h:
            index = int((y - field_h) / row_h)
            if index >= len(self._results):
                index = -1
        if index != self.hover:
            self.hover = index
            self.redraw()
        return False

    def _on_key(self, widget, event):
        """Escape closes the panel."""
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def on_click(self, x, y, button):
        field_h = self.field_height()
        row_h = 30 * self.metrics.scale
        if y < field_h:
            return False
        index = int((y - field_h) / row_h)
        if 0 <= index < len(self._results):
            self._launch(self._results[index])
            return True
        if index == len(self._results) and getattr(self, "_ask_row", None):
            self._ask()
            return True
        return False

    def _ask(self):
        """Hand the question to the assistant."""
        text = self.entry.get_text().strip()
        if not text:
            return
        self.close()
        self.shell.assistant.open("ask", question=text)
