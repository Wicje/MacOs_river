"""The assistant panel.

One floating window that does what the three macOS features do:

* **Ask**    a question, answered by the local model,
* **Write**  the Writing Tools: rewrite, proofread, summarise, change tone,
* **Screen** Visual Intelligence: what is on the display right now.

The model runs on this machine, so the answers never leave it.
"""

from __future__ import annotations

import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from ..macui import ai, draw  # noqa: E402
from ..macui import panel  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

WIDTH = 520
HEIGHT = 460

MODES = [
    ("ask", "Ask"),
    ("write", "Write"),
    ("screen", "Screen"),
]


class Assistant(Panel):
    NAMESPACE = "mac-assistant"

    def __init__(self, metrics, shell):
        super().__init__(
            metrics,
            layer="overlay",
            anchors={"top": True, "left": True},
            keyboard=False,
        )
        self.shell = shell
        self.mode = "ask"
        self.question = ""
        self.source = ""
        self.answer = ""
        self.error = ""
        self.busy = False
        self._buttons: list = []
        self._rows: list = []
        width = int(WIDTH * metrics.scale)
        height = int(HEIGHT * metrics.scale)
        screen_w = metrics.width or 1366
        screen_h = metrics.height or 768
        self.set_content_size(width, height)
        self.set_position(int((screen_w - width) / 2),
                          int((screen_h - height) / 2))
        self._entry = Gtk.Entry()
        self._entry.set_has_frame(False)
        self._entry.set_can_focus(True)
        self._entry.set_placeholder_text("Ask anything…")
        self._entry.connect("activate", lambda _e: self._ask())
        self.apply_style()
        self.remove(self.area)
        fixed = Gtk.Fixed()
        fixed.put(self.area, 0, 0)
        fixed.put(self._entry, int(20 * metrics.scale), int(12 * metrics.scale))
        self.add(fixed)

    def apply_style(self):
        """The text field follows the theme."""
        panel.apply_entry_css(panel.entry_css(
            self.metrics.config.get("theme", "dark"), 15))

    # -- lifecycle -----------------------------------------------------------

    def open(self, mode="ask", question="", source=""):
        self.mode = mode if mode in ("ask", "write", "screen") else "ask"
        self.question = question
        self.source = source
        self.answer = ""
        self.error = ""
        self.busy = False
        self.show_all()
        self._entry.grab_focus()
        if mode == "write" and source:
            self._run_write(source)
        self.redraw()

    def close(self):
        self.hide()

    def toggle(self, mode="ask"):
        if self.get_visible():
            self.close()
        else:
            self.open(mode)

    # -- the work ------------------------------------------------------------

    def _run(self, kind, prompt, system=None, images=None):
        self.busy = True
        self.answer = ""
        self.error = ""
        self.redraw()

        def work():
            answer, error = ai.chat(kind, prompt, system=system, images=images)
            GLib.idle_add(self._done, answer, error)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, answer, error):
        self.busy = False
        self.answer = answer or ""
        self.error = error or ""
        self.redraw()
        return False

    def _run_write(self, text):
        action, prompt = ai.write_actions(text)[0]
        self.source = text
        self._run("write", f"{prompt}\n\n{text}")

    def _run_screen(self):
        images = ai.screenshot()
        if images is None:
            self.error = "The screen could not be captured."
            self.redraw()
            return
        self._run("screen", "What is on my screen?", images=images)

    def _ask(self):
        text = self._entry.get_text().strip()
        if not text:
            return
        self.question = text
        self._entry.set_text("")
        self._run("ask", text)

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        scale = m.scale

        cr.save()
        draw.rounded_path(cr, 0, 0, width, height, 12 * scale)
        cr.clip()
        dark = m.config.get("theme", "dark") == "dark"
        cr.set_source_rgba(0.09, 0.09, 0.11, 1.0 if dark else 0.99)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.restore()
        draw.stroke_squircle(cr, 0, 0, width, height, 12 * scale,
                             pal["separator"], 1.0, m.squareness)

        self._buttons = []
        self._rows = []

        # -- the traffic lights (on the right, the text field has the left) --
        light = 12 * scale
        for index, colour in enumerate(((1.0, 0.23, 0.19), (1.0, 0.62, 0.0),
                                        (0.30, 0.80, 0.20))):
            cx = width - 16 * scale - (3 - index) * (light + 7 * scale)
            cy = 16 * scale
            draw.fill_squircle(cr, cx, cy, light, light, light / 2,
                               (*colour, 0.92), 2.0)
            self._rows.append((cx, cy, light, light,
                                lambda _x=None, index=index: self._light(index)))

        # -- the modes ------------------------------------------------------
        y = 40 * scale
        for index, (mode, label) in enumerate(MODES):
            bx = 90 * scale + index * 92 * scale
            active = self.mode == mode
            draw.fill_squircle(cr, bx, y, 84 * scale, 24 * scale, 12 * scale,
                               pal["accent"] if active else pal["fill_hover"],
                               2.0)
            draw.draw_text(cr, bx + 42 * scale, y + 12 * scale, label,
                           m.font("cc_font_size"),
                           pal["on_accent"] if active else pal["text"],
                           align="center", baseline="middle")
            self._rows.append((bx, y, 84 * scale, 24 * scale,
                                lambda _x=None, mode=mode: self._set_mode(mode)))

        # -- the source of the answer --------------------------------------
        y = 84 * scale
        if self.source:
            draw.draw_text(cr, 20 * scale, y, "Text", 11 * scale,
                           pal["text_faint"], baseline="middle")
            y += 20 * scale
            used = draw.draw_paragraph(cr, 20 * scale, y, width - 40 * scale,
                                       self.source, 11 * scale, pal["text_dim"],
                                       line_height=16 * scale, max_lines=3)
            y += used + 10 * scale

        # -- the answer -----------------------------------------------------
        if self.error:
            draw.draw_text(cr, 20 * scale, y, self.error, 11 * scale,
                           (1.0, 0.45, 0.35, 1.0), baseline="middle")
        elif self.busy:
            draw.draw_text(cr, 20 * scale, y, "Thinking…", 11 * scale,
                           pal["text_dim"], baseline="middle")
        elif self.answer:
            draw.draw_paragraph(cr, 20 * scale, y, width - 40 * scale,
                                self.answer, 12 * scale, pal["text"],
                                line_height=18 * scale)

        # -- the buttons at the bottom --------------------------------------
        by = height - 46 * scale
        labels = [("Copy", self._copy), ("Close", self.close)]
        for index, (label, action) in enumerate(labels):
            bw = 84 * scale
            bx = 20 * scale + index * (bw + 10 * scale)
            draw.fill_squircle(cr, bx, by, bw, 26 * scale, 13 * scale,
                               pal["fill_hover"], 2.0)
            draw.draw_text(cr, bx + bw / 2, by + 13 * scale, label,
                           11 * scale, pal["text"], align="center",
                           baseline="middle")
            self._buttons.append((bx, by, bw, 26 * scale, action))

        # the writing tools, when there is text to work on
        if self.source and not self.busy:
            x = 20 * scale
            for label, prompt in ai.write_actions(self.source):
                bw = draw.text_width(cr, label, 10 * scale) + 16 * scale
                if x + bw > width - 20 * scale:
                    break
                draw.fill_squircle(cr, x, by + 32 * scale, bw, 20 * scale,
                                   10 * scale, pal["fill"], 2.0)
                draw.draw_text(cr, x + bw / 2, by + 42 * scale, label,
                               10 * scale, pal["text_dim"], align="center",
                               baseline="middle")
                self._buttons.append((x, by + 32 * scale, bw, 20 * scale,
                                       (lambda _x=None, prompt=prompt:
                                        self._run("write",
                                                  f"{prompt}\n\n{self.source}"))))
                x += bw + 8 * scale

    def _set_mode(self, mode):
        self.mode = mode
        if mode == "screen":
            self._run_screen()
        elif mode == "write":
            if not self.source:
                self.source = self._clipboard()
            if self.source:
                self._run_write(self.source)
            else:
                self.error = "There is no text in the clipboard."
        self.redraw()

    def _light(self, index):
        if index == 0:
            self.close()

    def _clipboard(self):
        try:
            out = subprocess.run(["wl-paste", "--no-newline"],
                                 capture_output=True, text=True,
                                 timeout=3).stdout
        except Exception:  # noqa: BLE001
            return ""
        return out.strip()

    def _copy(self):
        if not self.answer:
            return
        subprocess.Popen(["wl-copy"], input=self.answer.encode(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- input ---------------------------------------------------------------

    def on_click(self, x, y, button):
        for bx, by, bw, bh, action in self._buttons:
            if bx <= x <= bx + bw and by <= y <= by + bh:
                action()
                return True
        for rx, ry, rw, rh, action in self._rows:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                action(x)
                return True
        return False

    def on_scroll(self, x, y, direction):
        return False
