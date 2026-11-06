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
        ("Start or stop dictation", ("sh", "-c", "~/.config/macshell/bin/dictate")),
        ("Edge Light: cycle off, auto, on", _fifo(fifo, "edgelight")),
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
        bool(re.search(r"[+\-*/%]", stripped))


# the measures Spotlight converts, each in its own family, every unit
# written as how many of the family's base it is
_UNITS = {
    "length": {
        "mm": 0.001, "millimetre": 0.001, "millimeter": 0.001,
        "cm": 0.01, "centimetre": 0.01, "centimeter": 0.01,
        "m": 1.0, "metre": 1.0, "meter": 1.0,
        "km": 1000.0, "kilometre": 1000.0, "kilometer": 1000.0,
        "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
        "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
        "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
        "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
        "nmi": 1852.0, "nautical mile": 1852.0,
    },
    "mass": {
        "mg": 1e-6, "g": 0.001, "gram": 0.001, "grams": 0.001,
        "kg": 1.0, "kilogram": 1.0, "kilograms": 1.0,
        "t": 1000.0, "tonne": 1000.0, "ton": 1000.0,
        "oz": 0.028349523125, "ounce": 0.028349523125,
        "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237,
        "pounds": 0.45359237, "st": 6.35029318, "stone": 6.35029318,
    },
    "volume": {
        "ml": 0.001, "millilitre": 0.001, "milliliter": 0.001,
        "l": 1.0, "litre": 1.0, "liter": 1.0, "litres": 1.0,
        "liters": 1.0,
        "tsp": 0.00492892159375, "teaspoon": 0.00492892159375,
        "tbsp": 0.01478676478125, "tablespoon": 0.01478676478125,
        "floz": 0.0295735295625, "fluid ounce": 0.0295735295625,
        "cup": 0.2365882365, "cups": 0.2365882365,
        "pt": 0.473176473, "pint": 0.473176473,
        "qt": 0.946352946, "quart": 0.946352946,
        "gal": 3.785411784, "gallon": 3.785411784, "gallons": 3.785411784,
    },
    "speed": {
        "m/s": 1.0, "kph": 1 / 3.6, "km/h": 1 / 3.6, "kmh": 1 / 3.6,
        "mph": 0.44704, "kn": 0.514444, "knot": 0.514444,
        "knots": 0.514444,
    },
    "data": {
        "b": 1.0, "byte": 1.0, "bytes": 1.0,
        "kb": 1000.0, "mb": 1e6, "gb": 1e9, "tb": 1e12,
        "kib": 1024.0, "mib": 1024.0 ** 2, "gib": 1024.0 ** 3,
        "tib": 1024.0 ** 4,
    },
    "time": {
        "ms": 0.001, "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0,
        "seconds": 1.0, "min": 60.0, "mins": 60.0, "minute": 60.0,
        "minutes": 60.0, "h": 3600.0, "hr": 3600.0, "hour": 3600.0,
        "hours": 3600.0, "day": 86400.0, "days": 86400.0,
        "week": 604800.0, "weeks": 604800.0,
    },
}

_TEMP = {"c": "c", "°c": "c", "celsius": "c",
         "f": "f", "°f": "f", "fahrenheit": "f",
         "k": "k", "kelvin": "k"}


def _norm_unit(name):
    return name.strip().lower().lstrip("°").replace("degrees ", "")


def _fmt_number(value):
    """An answer written the way a person would: whole numbers whole."""
    if isinstance(value, int) or (isinstance(value, float)
                                  and value.is_integer()):
        return f"{int(value)}"
    if isinstance(value, float) and (abs(value) >= 1e12
                                     or 0 < abs(value) < 1e-4):
        return f"{value:.6g}"
    return f"{round(value, 6)}"


_CONVERT_RE = re.compile(
    r"^\s*(-?\d[\d,._]*)\s*([a-z°][a-z°%/ ]*?)\s+(?:to|in|as)\s+"
    r"([a-z°][a-z°%/ ]*?)\s*$", re.IGNORECASE)


def _convert(text):
    """A measure turned into its other unit: 10 km to mi is 6.21371 mi.

    The table is local, so no program is asked and the answer comes at
    the speed of a keystroke; only the families written above answer.
    """
    match = _CONVERT_RE.match(text)
    if not match:
        return None
    raw, source, target = match.groups()
    try:
        amount = float(raw.replace(",", "").replace("_", ""))
    except ValueError:
        return None
    source, target = _norm_unit(source), _norm_unit(target)
    if source == target:
        return None

    if source in _TEMP and target in _TEMP:
        kelvin = {"c": amount + 273.15,
                  "f": (amount - 32) * 5 / 9 + 273.15,
                  "k": amount}[_TEMP[source]]
        result = {"c": kelvin - 273.15,
                  "f": (kelvin - 273.15) * 9 / 5 + 32,
                  "k": kelvin}[_TEMP[target]]
        answer = _fmt_number(result)
        shown = f"{answer}°{target.upper()}"
        return shown, shown

    for family in _UNITS.values():
        if source in family and target in family:
            result = amount * family[source] / family[target]
            answer = _fmt_number(result)
            return f"{answer} {target}", answer
    return None


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
        else:
            converted = _convert(text)
            if converted is not None:
                shown, _copied = converted
                results.append((f"= {shown}", shown, "calc"))

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
            if program == "sh" and "trash --empty" in " ".join(args):
                from ..macui import sound
                sound.play("trash")
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
