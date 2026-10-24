"""Spotlight-style search overlay.

A glass search card under the menu bar.  Typing filters the installed
applications and the folders in the home directory; clicking a result (or
pressing return) launches it.
"""

from __future__ import annotations

import ast
import operator
import os
import re
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from ..macui import apps, draw, glyphs, state  # noqa: E402
from ..macui import panel as panel_module  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

MAX_RESULTS = 7

# the projects of the desk, with the verbs each one offers: name, path,
# the last sentence about it that the rows show
PROJECTS = [
    ("macshell", "~/.config/macshell", "the macOS shell of this desk"),
    ("mac", "~/mac", "the pictures and reference of the desk"),
]


def _fifo(fifo, text):
    """A command through the fifo, safely: the shell interprets a small
    list of commands and never arbitrary text."""
    return ("sh", "-c",
            'printf "%s\\n" "{0}" > "{1}"'.format(text, fifo))


def _commands():
    """The palette: fixed verbs the shell runs directly."""
    fifo = os.environ.get("XDG_RUNTIME_DIR", "") + "/macshell.cmd"
    return [
        ("Open Launchpad", _fifo(fifo, "launchpad")),
        ("Show the clipboard history", _fifo(fifo, "clipboard")),
        ("Tile the window to the left", _fifo(fifo, "tile:left")),
        ("Tile the window to the right", _fifo(fifo, "tile:right")),
        ("Empty the Trash",
         ("sh", "-c", "gio trash --empty 2>/dev/null || true")),
        ("Lock the screen",
         ("sh", "-c", "~/.config/river/lock.sh")),
    ]

# the arithmetic Spotlight can do, and the operations it is allowed to
_CALC_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}


import difflib

# fuzzy ranking collar: the ratio between the typed text and the label,
# with an extra point for a prefix and for the programs that were
# recently in front
def _score(label, needle):
    low = label.lower()
    if low.startswith(needle):
        return 0.0
    within = low.find(needle)
    if within > 0:
        return 0.2 + within * 0.01
    return 1.0 - difflib.SequenceMatcher(None, low, needle).ratio()


def _calc(text):
    """Arithmetic like macOS does in Spotlight: 2*(3+4) is 14.

    The text is read as a tree, and only the operations in the table
    above are allowed to stand in the tree, so no program text of the
    user is ever run.
    """
    if not re.search(r"\d", text) or not re.search(r"[-+*/%(]", text):
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError):
        return None

    def value(node):
        if isinstance(node, ast.Expression):
            return value(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not \
                    isinstance(node.value, bool):
                return node.value
            return None
        if isinstance(node, ast.UnaryOp):
            operand = value(node.operand)
            if operand is None:
                return None
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
            return None
        if isinstance(node, ast.BinOp):
            left, right = value(node.left), value(node.right)
            if left is None or right is None:
                return None
            operation = _CALC_OPS.get(type(node.op))
            if operation is None:
                return None
            try:
                return operation(left, right)
            except (ZeroDivisionError, OverflowError):
                return None
        return None

    result = value(tree)
    if result is None:
        return None
    if isinstance(result, int) or (isinstance(result, float)
                                   and result.is_integer()):
        return f"{int(result)}"
    return f"{round(result, 6)}"


def _calc_query(text):
    """True when the text of the field is an arithmetic question."""
    stripped = text.strip()
    return bool(re.fullmatch(r"[\d()\s\+\-\*/%.]+", stripped)) and \
        bool(re.search(r"\d", stripped)) and \
        bool(re.search(r"[+\-*/]", stripped))


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
        answer = _calc(text) if _calc_query(text) else None
        if answer is not None:
            results.append((f"= {answer}", answer, "calc"))

        # the projects of the desk, with the verbs they offer
        results.extend(self._projects(text))
        # the history of the clipboard, when the word asked for it
        results.extend(self._clipboard_rows(text))

        # the palette, the apps and the folders of home, fuzzy and
        # ranked: a prefix wins, being recently in front wins, and a
        # far-off match is dropped instead of buried
        recent = state.recent_apps()
        ranked = []
        for label, payload in _commands():
            score = _score(label, needle)
            if score > 0.42:
                continue
            ranked.append((score, label, payload, "command"))
        for entry in apps.all_applications():
            label = entry.get("name") or ""
            score = _score(label, needle)
            if score > 0.42:
                continue
            for index, app_id in enumerate(recent):
                if state.friendly_name(app_id).lower() == label.lower():
                    score -= max(0.02, 0.18 - index * 0.03)
            ranked.append((score, label, entry.get("exec") or "", "app"))
        ranked.sort(key=lambda row: (row[0], row[1].lower()))
        results.extend((label, command, kind)
                       for score, label, command, kind in ranked)

        home = os.path.expanduser("~")
        try:
            for entry in sorted(os.listdir(home))[:400]:
                if needle in entry.lower():
                    results.append((entry, os.path.join(home, entry),
                                    "folder"))
        except OSError:
            pass
        results = results[:MAX_RESULTS]
        results.append((f"Search the web for “{text}”", text, "web"))
        return results

    def _projects(self, text):
        """The rows a project offers when its name has been typed."""
        needle = text.lower()
        rows = []
        for name, path, _tagline in PROJECTS:
            if needle in name:
                payload = os.path.expanduser(path)
                rows.append((f"Open {name} in Finder", payload, "project"))
                rows.append((f"Terminal at {name}",
                             payload, "project-terminal"))
        return rows

    def _clipboard_rows(self, text):
        """The last entries of the clipboard, for the word clipboard."""
        if "clipboard" not in text.lower():
            return []
        out = state.run("cliphist list")
        rows = []
        for line in out.splitlines()[:4]:
            entry_id, _, piece = line.partition("\t")
            if not piece:
                continue
            rows.append((piece.strip()[:60] or "an image",
                         entry_id, "clip"))
        return rows

    def _projects(self, text):
        """The rows a project offers when its name has been typed."""
        needle = text.lower()
        rows = []
        for name, path, tagline in PROJECTS:
            if needle in name:
                payload = os.path.expanduser(path)
                rows.append((f"Open {name} in Finder", payload, "project"))
                rows.append((f"Terminal at {name}",
                             payload, "project-terminal"))
        return rows

    def _clipboard_rows(self, text):
        """The last entries of the clipboard, for the word clipboard."""
        if "clipboard" not in text.lower():
            return []
        out = run("cliphist list")
        rows = []
        for line in out.splitlines()[:4]:
            entry_id, _, piece = line.partition("\t")
            if not piece:
                continue
            rows.append((piece.strip()[:60] or "an image",
                         entry_id, "clip"))
        return rows

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
        if kind == "clip":
            # the entry of the history back to the clipboard
            subprocess.Popen(["sh", "-c", "cliphist decode | wl-copy"],
                             input=command.encode(),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.close()
            return
        if kind == "command":
            program, *args = command
            subprocess.Popen([program, *args], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.close()
            return
        if kind == "project-terminal":
            subprocess.Popen(["foot", "-D", command],
                             start_new_session=True,
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
                           "calc": "Calculator", "web": "Web",
                           "clip": "Clipboard", "command": "Command",
                           "project": "Project",
                           "project-terminal": "Terminal"}.get(kind, "")
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
