#!/usr/bin/env python3
"""River UI - night light.

A full-screen, click-through warm tint (there is no gamma/clamp tool on
this system). Re-run to toggle off. Optional alpha via argv[1].
"""

import os
import sys

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, Gtk, GtkLayerShell  # noqa: E402

PIDFILE = f"/tmp/river-night-{os.getuid()}.pid"
ALPHA = float(sys.argv[1]) if len(sys.argv) > 1 else 0.14


class NightLight(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "nightlight")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        GtkLayerShell.set_keyboard_interactivity(
            self, GtkLayerShell.KeyboardMode.NONE)

        area = Gtk.DrawingArea()
        area.connect("draw", self.on_draw)
        self.add(area)
        self.connect("realize", self.make_click_through)

    def make_click_through(self, *_a):
        region = cairo.Region()
        gdk_win = self.get_window()
        if gdk_win is not None:
            gdk_win.input_shape_combine_region(region, 0, 0)

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(1.0, 0.55, 0.18, ALPHA)
        cr.paint()
        return False


def main():
    if os.path.exists(PIDFILE):
        try:
            os.kill(int(open(PIDFILE).read().strip()), 15)
            return 0
        except (ValueError, OSError):
            pass
    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))
    win = NightLight()
    win.show_all()
    Gtk.main()
    try:
        os.remove(PIDFILE)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
