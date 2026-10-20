"""Base class for the shell's layer-shell panels.

Every panel is a transparent GTK window anchored to the compositor's layer
shell and painted entirely with Cairo.  Panels are cheap to add: the whole
shell runs inside one Python process, so four panels cost roughly what one
used to.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402


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
        self.connect("destroy", Gtk.main_quit)

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
