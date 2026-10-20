#!/usr/bin/env python3
"""River UI wallpaper daemon (GTK3 + gtk-layer-shell).

The desktop shows a gallery of wallpapers and moves to the next one every
thirty seconds, crossfading between them.  Pictures in ``~/mac`` and
``~/Pictures/wall`` are picked up automatically, and picking a wallpaper by
hand (Super+Shift+P) simply moves the gallery on to that picture.

Modes:
  * animated GIF/WebP  -> played back in place
  * static image       -> crossfaded with the next one
  * live aurora        -> when the gallery is empty
"""

import json
import math
import os
import subprocess
import sys
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import GLib, Gdk, GdkPixbuf, Gtk, GtkLayerShell  # noqa: E402

STATE = os.path.expanduser("~/.config/river/.wallpaper")
SHELL_CONFIG = os.path.expanduser("~/.config/macshell/config.json")
DEFAULT_IMAGE = os.path.expanduser("~/Pictures/wall/tahoe-purple.png")
GALLERY_DIRS = ("~/mac", "~/Pictures/wall")

ROTATE_SECONDS = 30.0
FADE_SECONDS = 1.6
FPS = 12

_windows = []
_areas = []
_start = time.monotonic()


def _gallery():
    """Every picture in the gallery, in a stable order."""
    found = []
    for directory in GALLERY_DIRS:
        directory = os.path.expanduser(directory)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp",
                                          ".gif")):
                continue
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                found.append(path)
    return found


class Wallpaper:
    """A picture, either a still frame or an animation."""

    def __init__(self, path):
        self.path = path
        self.static = None
        self._anim = None
        self._iter = None
        self.frame = None
        self.load()

    def load(self):
        try:
            anim = GdkPixbuf.PixbufAnimation.new_from_file(self.path)
            if anim.is_static_image():
                self.static = GdkPixbuf.Pixbuf.new_from_file(self.path)
            else:
                self._anim = anim
                self._iter = anim.get_iter(None)
                self.frame = self._iter.get_pixbuf()
        except Exception:  # noqa: BLE001
            self.static = None
            self._anim = None
            self._iter = None
            self.frame = None

    @property
    def animated(self):
        return self._iter is not None

    def advance(self):
        """Step the animation; returns True when a new frame was produced."""
        if self._iter is None:
            return False
        try:
            if self._iter.advance(None):
                self.frame = self._iter.get_pixbuf()
                return True
        except Exception:  # noqa: BLE001
            self._iter = None
        return False

    def pixbuf(self):
        return self.static if self.static is not None else self.frame


class Gallery:
    """The rotating collection of wallpapers."""

    def __init__(self):
        self.items = []
        self.index = 0
        self.current = None
        self.incoming = None
        self.fade = 0.0
        self.next_switch = 0.0
        self.pinned = None
        self._state_checked = 0.0

    def load(self):
        self.items = _gallery()
        if not self.items:
            return False
        chosen = self._read_state()
        if chosen and chosen in self.items:
            self.index = self.items.index(chosen)
        else:
            self.index = 0
            self._write_state()
        self.current = Wallpaper(self.items[self.index])
        self.incoming = None
        self.fade = 0.0
        self.next_switch = time.monotonic() + ROTATE_SECONDS
        return True

    def _read_state(self):
        try:
            with open(STATE) as fh:
                return fh.read().strip()
        except OSError:
            return ""

    def _write_state(self):
        try:
            with open(STATE, "w") as fh:
                fh.write(self.items[self.index] + "\n")
        except OSError:
            pass

    def rotation_enabled(self):
        """Whether the shell wants the wallpaper to rotate."""
        try:
            with open(SHELL_CONFIG) as fh:
                return bool(json.load(fh).get("wallpaper_rotate", True))
        except (OSError, ValueError):
            return True

    def follow_state(self):
        """Honour a wallpaper that was picked by hand."""
        now = time.monotonic()
        if now - self._state_checked < 1.0:
            return
        self._state_checked = now
        chosen = self._read_state()
        if not chosen or chosen == self.items[self.index]:
            return
        if chosen not in self.items:
            self.items.append(chosen)
            self.index = len(self.items) - 1
        else:
            self.index = self.items.index(chosen)
        self.current = Wallpaper(self.items[self.index])
        self.incoming = None
        self.fade = 0.0
        self.next_switch = now + ROTATE_SECONDS

    def start_fade(self):
        if len(self.items) < 2:
            self.next_switch = time.monotonic() + ROTATE_SECONDS
            return
        self.index = (self.index + 1) % len(self.items)
        self._write_state()
        self.incoming = Wallpaper(self.items[self.index])
        self.fade = 0.0

    def tick(self, now):
        """Advance the gallery; returns True when something was redrawn."""
        dirty = False
        if self.current is not None and self.current.advance():
            dirty = True

        self.follow_state()

        if self.incoming is not None:
            self.fade += 1.0 / (FADE_SECONDS * FPS)
            if self.incoming.advance():
                dirty = True
            if self.fade >= 1.0:
                self.current = self.incoming
                self.incoming = None
                self.fade = 0.0
                self.next_switch = now + ROTATE_SECONDS
            dirty = True
        elif now >= self.next_switch:
            if self.rotation_enabled():
                self.start_fade()
            else:
                self.next_switch = now + ROTATE_SECONDS

        return dirty


gallery = Gallery()


# --- live aurora (used when there is nothing to show) -----------------------

def _radial(ctx, cx, cy, r, stops):
    g = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
    for pos, col in stops:
        g.add_color_stop_rgba(pos, col[0], col[1], col[2], col[3])
    ctx.set_source(g)
    ctx.paint()


def _paint_live(ctx, w, h):
    t = time.monotonic() - _start
    phase = t * 0.15

    g = cairo.LinearGradient(0, 0, 0, h)
    g.add_color_stop_rgb(0.00, 0.06, 0.02, 0.14)
    g.add_color_stop_rgb(0.18, 0.16, 0.05, 0.34)
    g.add_color_stop_rgb(0.42, 0.34, 0.14, 0.58)
    g.add_color_stop_rgb(0.62, 0.30, 0.12, 0.52)
    g.add_color_stop_rgb(1.00, 0.05, 0.02, 0.11)
    ctx.set_source(g)
    ctx.paint()

    cx = w * (0.60 + 0.07 * math.sin(phase * 0.7))
    cy = h * (0.42 + 0.06 * math.cos(phase * 0.9))
    r = w * (0.80 + 0.04 * math.sin(phase * 0.5))
    _radial(ctx, cx, cy, r, [
        (0.00, (0.62, 0.38, 0.92, 0.85)),
        (0.35, (0.48, 0.24, 0.78, 0.55)),
        (1.00, (0.30, 0.10, 0.55, 0.00)),
    ])

    cx2 = w * (0.70 + 0.09 * math.cos(phase * 0.8 + 1.3))
    cy2 = h * (0.30 + 0.07 * math.sin(phase * 0.6 + 0.7))
    _radial(ctx, cx2, cy2, w * 0.32, [
        (0.00, (0.86, 0.66, 1.00, 0.48)),
        (1.00, (0.70, 0.45, 0.98, 0.00)),
    ])

    cx3 = w * (0.14 + 0.05 * math.sin(phase * 0.5 + 2.0))
    cy3 = h * (0.18 + 0.05 * math.cos(phase * 0.7 + 1.0))
    _radial(ctx, cx3, cy3, w * 0.40, [
        (0.00, (0.45, 0.10, 0.55, 0.35)),
        (1.00, (0.25, 0.05, 0.40, 0.00)),
    ])

    g = cairo.RadialGradient(w * 0.5, h * 0.48, w * 0.30,
                             w * 0.5, h * 0.48, w * 0.90)
    g.add_color_stop_rgba(0.0, 0, 0, 0, 0.0)
    g.add_color_stop_rgba(1.0, 0.02, 0.0, 0.06, 0.55)
    ctx.set_source(g)
    ctx.paint()


# --- painting ---------------------------------------------------------------

def _draw_pixbuf(ctx, w, h, pb, alpha=1.0):
    if pb is None:
        return
    iw, ih = pb.get_width(), pb.get_height()
    if iw <= 0 or ih <= 0:
        return
    ctx.save()
    if alpha < 1.0:
        ctx.push_group()
    ctx.scale(w / iw, h / ih)
    Gdk.cairo_set_source_pixbuf(ctx, pb, 0, 0)
    ctx.paint()
    if alpha < 1.0:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(alpha)
    ctx.restore()


def on_draw(widget, cr, _data=None):
    alloc = widget.get_allocation()
    w, h = alloc.width, alloc.height
    if w <= 0 or h <= 0:
        return False

    current = gallery.current
    if current is None:
        _paint_live(cr, w, h)
        return False

    _draw_pixbuf(cr, w, h, current.pixbuf())
    if gallery.incoming is not None and gallery.fade > 0:
        _draw_pixbuf(cr, w, h, gallery.incoming.pixbuf(), gallery.fade)
    return False


def _tick():
    now = time.monotonic()
    if gallery.tick(now):
        for area in _areas:
            area.queue_draw()
    return True


def make_window(monitor):
    win = Gtk.Window()
    win.set_decorated(False)
    win.set_title("wallpaper")
    win.set_skip_taskbar_hint(True)
    win.set_skip_pager_hint(True)

    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "wallpaper")
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.BACKGROUND)
    for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                 GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(win, edge, True)
    GtkLayerShell.set_exclusive_zone(win, -1)
    if monitor is not None:
        GtkLayerShell.set_monitor(win, monitor)

    area = Gtk.DrawingArea()
    area.connect("draw", on_draw)
    _areas.append(area)
    win.add(area)

    win.connect("destroy", Gtk.main_quit)
    return win


def main():
    gallery.load()

    display = Gdk.Display.get_default()
    for i in range(display.get_n_monitors()):
        _windows.append(make_window(display.get_monitor(i)))
    for win in _windows:
        win.show_all()

    GLib.timeout_add(max(16, int(1000 / FPS)), _tick)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
