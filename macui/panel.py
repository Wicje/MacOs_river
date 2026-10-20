"""Base class for the shell's layer-shell panels.

Every panel is a transparent GTK window anchored to the compositor's layer
shell and painted entirely with Cairo.  Panels are cheap to add: the whole
shell runs inside one Python process, so four panels cost roughly what one
used to.
"""

from __future__ import annotations

import ctypes

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402


# --- input regions ---------------------------------------------------------
#
# GDK keeps GdkRegion to itself, so the region is built with cairo and
# handed over with ctypes.  Since GDK 3.22 a GdkRegion *is* a cairo
# region, so the two libraries understand each other.

class _RectInt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("width", ctypes.c_int), ("height", ctypes.c_int)]


def _load_shape_api():
    try:
        cairo = ctypes.CDLL("libcairo.so.2")
        gdk = ctypes.CDLL("libgdk-3.so.0")
        cairo.cairo_region_create.restype = ctypes.c_void_p
        cairo.cairo_region_create.argtypes = []
        cairo.cairo_region_union_rectangle.restype = ctypes.c_int
        cairo.cairo_region_union_rectangle.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_RectInt)]
        cairo.cairo_region_destroy.argtypes = [ctypes.c_void_p]
        gdk.gdk_window_input_shape_combine_region.restype = None
        gdk.gdk_window_input_shape_combine_region.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        capsule = ctypes.pythonapi.PyCapsule_GetPointer
        capsule.restype = ctypes.c_void_p
        capsule.argtypes = [ctypes.py_object, ctypes.c_char_p]
        return cairo, gdk, capsule
    except Exception:  # noqa: BLE001
        return None, None, None


_CAIRO, _GDK, _CAPSULE = _load_shape_api()


ENTRY_CSS = """
entry {
    background: transparent;
    border: none;
    color: __COLOUR__;
    caret-color: __COLOUR__;
    font-family: "SF Pro Text";
    font-size: __SIZE__px;
    padding: 0;
}
entry:focus { box-shadow: none; outline: none; }
"""


def entry_css(theme="dark", size=15):
    """The style of the text fields, in the colours of the theme."""
    colour = "#ffffff" if theme == "dark" else "#1b1b21"
    return (ENTRY_CSS.replace("__COLOUR__", colour)
            .replace("__SIZE__", str(size)).encode())


def apply_entry_css(css):
    """Make the style of the text fields known to the whole screen."""
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class Panel(Gtk.Window):
    """A layer-shell surface drawn with Cairo."""
    NAMESPACE = "mac-panel"

    def __init__(self, metrics, *, layer="overlay", anchors=None, margins=None,
                 exclusive=0, keyboard=False, namespace=None):
        super().__init__()
        self.metrics = metrics
        self.pointer = (-1, -1)
        self.hovered = -1
        self.size_override = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)

        self._slide_edge = "bottom"
        self._slide_value = 0.0
        self._slide_target = 0.0
        self._slide_timer = None
        self._slide_done = None

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, namespace or self.NAMESPACE)
        GtkLayerShell.set_layer(
            self, getattr(GtkLayerShell.Layer, layer.upper(), GtkLayerShell.Layer.OVERLAY)
        )
        for edge, on in (anchors or {}).items():
            GtkLayerShell.set_anchor(self, getattr(GtkLayerShell.Edge, edge.upper()), on)
        for edge, value in (margins or {}).items():
            GtkLayerShell.set_margin(self, getattr(GtkLayerShell.Edge, edge.upper()), value)
        if exclusive:
            GtkLayerShell.set_exclusive_zone(self, exclusive)
        GtkLayerShell.set_keyboard_interactivity(
            self,
            GtkLayerShell.KeyboardMode.EXCLUSIVE if keyboard
            else GtkLayerShell.KeyboardMode.NONE,
        )

        self.area = Gtk.DrawingArea()
        self.area.set_has_window(False)
        self.area.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.add(self.area)

        # A drawing area without its own GdkWindow never sees pointer
        # events: they are delivered to the toplevel window instead.  The
        # handlers therefore live on the window, and the window carries the
        # event mask.
        self.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-press-event", self._on_button)
        self.connect("button-release-event", self._on_button)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("scroll-event", self._on_scroll)
        self.connect("map-event", self._on_map)
        self.connect("destroy", Gtk.main_quit)

    # -- the input region ----------------------------------------------------
    #
    # A layer shell surface takes the pointer over its whole rectangle, even
    # where it is transparent.  A dock that lives in a tall surface would
    # therefore swallow the clicks of every window underneath it.  The
    # panels that draw a small card inside a big surface say which
    # rectangles should take the pointer; the rest of the surface is
    # transparent to the pointer.

    def input_rects(self):
        """The rectangles of the surface that take the pointer.

        None means the whole surface.  Return a list of (x, y, w, h) tuples
        in the surface's own coordinates.
        """
        return None

    def update_input_region(self):
        """Apply the input rectangles to the surface."""
        rects = self.input_rects()
        if not rects or _GDK is None:
            return
        window = self.get_window()
        if window is None:
            return
        region = None
        try:
            region = _CAIRO.cairo_region_create()
            for x, y, w, h in rects:
                if w <= 0 or h <= 0:
                    continue
                rect = _RectInt(int(x), int(y), int(w), int(h))
                _CAIRO.cairo_region_union_rectangle(region, ctypes.byref(rect))
            pointer = _CAPSULE(window.__gpointer__, None)
            _GDK.gdk_window_input_shape_combine_region(pointer, region, 0, 0)
        except Exception:  # noqa: BLE001
            # a panel that cannot shape its input simply keeps the whole
            # surface, which is what the shell did before
            pass
        finally:
            if region:
                _CAIRO.cairo_region_destroy(region)

    def _on_map(self, *_args):
        # the surface only exists once the window is on screen
        self.update_input_region()
        return False

    # -- sliding -------------------------------------------------------------

    def slide(self, edge, target, done=None):
        """Animate the surface's margin on one edge.

        A negative margin pushes the surface off the screen, which is how
        the dock slides down and the notch slides up the way macOS does it.
        """
        self._slide_edge = edge
        self._slide_target = float(target)
        self._slide_done = done
        if self._slide_timer is None:
            self._slide_timer = GLib.timeout_add(16, self._slide_step)

    def _slide_step(self):
        current = self._slide_value
        target = self._slide_target
        if abs(target - current) < 1.0:
            self._slide_value = target
            self._apply_slide()
            self._slide_timer = None
            if self._slide_done:
                self._slide_done()
            return False
        self._slide_value = current + (target - current) * 0.4
        self._apply_slide()
        return True

    def _apply_slide(self):
        edge = getattr(GtkLayerShell.Edge, self._slide_edge.upper())
        GtkLayerShell.set_margin(self, edge, int(self._slide_value))

    # -- geometry helpers ---------------------------------------------------

    def _local(self, event):
        """Pointer position in the drawing area's own coordinates."""
        toplevel = self.area.get_toplevel()
        alloc = self.area.get_allocation()
        window = getattr(event, "window", None)
        if window is None or window == toplevel.get_window():
            # events delivered to the window are already in window space
            return event.x - alloc.x, event.y - alloc.y
        tx, ty = self.area.translate_coordinates(toplevel, event.x, event.y)
        return tx - alloc.x, ty - alloc.y

    # -- overridable hooks --------------------------------------------------

    def paint(self, cr, width, height):
        """Draw the panel.  Override in subclasses."""

    def on_motion(self, x, y):
        return False

    def on_click(self, x, y, button):
        return False

    def on_scroll(self, x, y, direction):
        return False

    def on_leave(self):
        return False

    # -- GTK plumbing -------------------------------------------------------

    def _on_draw(self, _widget, cr):
        alloc = self.area.get_allocation()
        if self.size_override:
            w, h = self.size_override
        else:
            w, h = alloc.width, alloc.height
        if w <= 0 or h <= 0:
            return False
        cr.save()
        cr.rectangle(0, 0, w, h)
        cr.clip()
        self.paint(cr, w, h)
        cr.restore()
        return False

    def _on_motion(self, _w, event):
        x, y = self._local(event)
        self.pointer = (x, y)
        self.on_motion(x, y)
        self.area.queue_draw()
        return False

    def _on_button(self, _w, event):
        x, y = self._local(event)
        if event.type == Gdk.EventType.BUTTON_PRESS:
            self.on_click(x, y, event.button)
        return False

    def _on_enter(self, _w, _event):
        self.area.queue_draw()
        return False

    def _on_leave(self, _w, _event):
        self.pointer = (-1, -1)
        self.on_leave()
        self.area.queue_draw()
        return False

    def _on_scroll(self, _w, event):
        x, y = self._local(event)
        direction = event.direction
        self.on_scroll(x, y, direction)
        return False

    # -- helpers ------------------------------------------------------------

    def content_size(self):
        """The size the panel should paint at."""
        if self.size_override:
            return self.size_override
        alloc = self.get_allocation()
        return (alloc.width, alloc.height)

    def redraw(self):
        self.area.queue_draw()

    def set_content_size(self, width, height):
        """Request a content size.

        The request is placed on the drawing area rather than the window:
        a window-level request makes GTK ignore the compositor's configure
        and collapse the surface to its natural size.
        """
        self.area.set_size_request(int(width), int(height))

    def set_position(self, x, y):
        """Move the surface by setting layer-shell margins."""
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, int(x))
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, int(y))

    def set_horizontal_offset(self, x):
        """Slide the surface sideways (used to centre a floating panel)."""
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, int(x))

    def toggle_visible(self):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
        return self.get_visible()

    def tick(self, interval_ms, callback):
        GLib.timeout_add(interval_ms, callback)
