#!/usr/bin/env python3
"""Render shell panels to PNG files without a compositor.

Usage:  python3 -m macshell.tools.render [panel ...] [--theme dark|light]

Useful for iterating on the visuals: every panel's paint() routine is
called against a plain Cairo surface, so the output is exactly what the
compositor would show for that region.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from macshell.macui.metrics import Metrics  # noqa: E402

OUT_DIR = os.path.expanduser("~/.local/share/macshell/preview")


def render(panel, width, height, path, zoom=1):
    panel.size_override = (int(width), int(height))
    width = int(width * zoom)
    height = int(height * zoom)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    if zoom != 1:
        cr.scale(zoom, zoom)
    # wallpaper-ish backdrop so translucency is visible
    cr.set_source_rgb(0.16, 0.14, 0.34)
    cr.paint()
    panel.paint(cr, width / zoom, height / zoom)
    surface.write_to_png(path)
    print(f"{path}  {width}x{height}")


def main():
    argv = sys.argv[1:]
    theme = "dark"
    if "--theme" in argv:
        index = argv.index("--theme")
        theme = argv[index + 1]
        del argv[index:index + 2]

    os.makedirs(OUT_DIR, exist_ok=True)
    metrics = Metrics()
    metrics.config["theme"] = theme
    metrics.width = 1366

    from macshell.panels.controlcenter import ControlCentre
    from macshell.panels.dock import Dock
    from macshell.panels.menubar import MenuBar
    from macshell.panels.widgets import Widgets

    class FakeShell:
        def toggle_control_center(self): pass
        def open_spotlight(self): pass
        def open_menu(self, *a): pass
        def toggle_apple_menu(self, *a): pass
        def set_theme(self, *a): pass

    shell = FakeShell()

    want = argv or ["menubar", "dock", "controlcenter", "widgets"]

    if "menubar" in want:
        bar = MenuBar(metrics, shell)
        bar.refresh()
        render(bar, 1366, int(metrics.px("menu_bar_height")),
               f"{OUT_DIR}/menubar-{theme}.png")
    if "dock" in want:
        dock = Dock(metrics, shell)
        render(dock, 1366, dock.panel_height(),
               f"{OUT_DIR}/dock-{theme}.png")
    if "controlcenter" in want:
        cc = ControlCentre(metrics, shell)
        cc.refresh()
        width = int(metrics.px("cc_width"))
        height = int(cc._height(width))
        zoom = 2 if "--zoom" in argv else 1
        if "--zoom" in argv:
            argv.remove("--zoom")
        render(cc, width, height, f"{OUT_DIR}/controlcenter-{theme}.png", zoom)
    if "widgets" in want:
        w = Widgets(metrics, shell)
        w.refresh()
        width = int(metrics.px("widget_width"))
        height = w.content_height()
        render(w, width, height, f"{OUT_DIR}/widgets-{theme}.png")
    if "glyphs" in want:
        from macshell.macui import glyphs
        names = ["apple", "spotlight", "control_center", "wifi", "bluetooth",
                 "moon", "display", "speaker", "airplay", "accessibility",
                 "grid", "check", "chevron_down"]
        cell = 64
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, cell * len(names), cell)
        cr = cairo.Context(surface)
        cr.set_source_rgb(0.16, 0.14, 0.34)
        cr.paint()
        for index, name in enumerate(names):
            fn = getattr(glyphs, name)
            fn(cr, index * cell + cell / 2 - 16, cell / 2 - 16, 32, (1, 1, 1, 1))
        surface.write_to_png(f"{OUT_DIR}/glyphs.png")
        print(f"{OUT_DIR}/glyphs.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
