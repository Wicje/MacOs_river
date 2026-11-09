"""The widget gallery: the sheet macOS opens when the dock says ``+``.

A glass sheet that floats just above the dock, the way macOS gives the
widget gallery the whole scene of the wallpaper to stand in front of:
the kinds of widgets in a rail at the left, the previews of every kind
in a grid at the right.  Clicking a preview puts the widget on the strip
above the dock or takes it away again; a red chip appears on the cards
the strip already carries.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import GLib, GtkLayerShell  # noqa: E402

from ..macui import draw, glyphs  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

from . import widgetstrip  # noqa: E402

# the categories of the rail, and the kind each card kind belongs to
CATEGORIES = (
    ("all", "All Widgets", "grid"),
    ("clock", "Clocks", "timer"),
    ("calendar", "Calendar", "timer"),
    ("sticky", "Reminders", "clipboard"),
    ("media", "Media", "speaker"),
    ("system", "System", "power"),
    ("weather", "Weather", "sun"),
)

CATEGORY_OF = {
    "clock": "clock", "analog": "clock", "calendar": "calendar",
    "sticky": "sticky", "media": "media", "battery": "system",
    "weather": "weather",
}


class WidgetGallery(Panel):
    NAMESPACE = "mac-widget-gallery"

    def __init__(self, metrics, shell):
        self.shell = shell
        self.ctx = {}
        self.category = "all"
        self.hovered = -1
        self.cells = []       # (kind, x, y, w, h) of every preview
        self.rows = []        # the rail rows, as the rail paints them
        self._tick_source = None
        self._sheet = (0, 0, 0, 0)
        self._close = (0, 0, 0, 0)
        super().__init__(metrics, layer="overlay", anchors={"bottom": True},
                         margins={"bottom": 100}, keyboard=False)
        self._layout()

    # -- geometry -------------------------------------------------------------

    def _sheet_size(self, m):
        s = m.scale
        width = int((12 * 2 + 200 + 18 + 3 * 168 + 2 * 12 + 18) * s)
        rows = -(-len(widgetstrip.KINDS) // 3)
        height = int((24 + 44 + 12
                      + rows * (66 + 24) + (rows - 1) * 12 + 18) * s)
        return width, height

    def _layout(self):
        """Place the rail, the previews and the close button."""
        m = self.metrics
        s = m.scale
        width, height = self._sheet_size(m)
        pad = 12 * s
        self._sheet = (pad, pad, width - pad * 2, height - pad * 2)
        x0, y0, w, h = self._sheet
        sidebar_w = 200 * s
        rail_y = y0 + 44 * s + 14 * s
        self.rows = []
        for index, (_kind, label, _glyph) in enumerate(CATEGORIES):
            self.rows.append(("cat", index, x0 + 12 * s,
                              rail_y + index * 34 * s,
                              sidebar_w - 24 * s, 28 * s))
        grid_x = x0 + sidebar_w + 18 * s
        cell_w, cell_h, cell_gap = 168 * s, (66 + 24) * s, 12 * s
        self.cells = []
        for entry in self._shown_kinds():
            col = len(self.cells) % 3
            row = len(self.cells) // 3
            self.cells.append(("cell", entry, grid_x + col * (cell_w + cell_gap),
                               y0 + 44 * s + 14 * s + row * (cell_h + cell_gap),
                               cell_w, cell_h))
        self._close = (x0 + w - 20 * s - 22 * s, y0 + 12 * s, 22 * s, 22 * s)
        self.set_content_size(width, height)

    def _shown_kinds(self):
        """The kinds the rail's category shows."""
        return [kind for kind in widgetstrip.KINDS
                if self.category == "all"
                or CATEGORY_OF[kind] == self.category]

    def _layout_size(self):
        return self._sheet_size(self.metrics)

    # -- state ------------------------------------------------------------------

    def refresh(self):
        self.ctx = widgetstrip.snapshot_ctx(self.metrics)
        self.redraw()

    def _ensure_tick(self, on):
        if on and self._tick_source is None:
            self._tick_source = GLib.timeout_add(1000, self._tick)
        elif not on and self._tick_source is not None:
            GLib.source_remove(self._tick_source)
            self._tick_source = None

    def _tick(self):
        if self.get_visible():
            self.refresh()
        return bool(self._tick_source)

    # -- the membership of the strip -------------------------------------------

    def _toggle_card(self, kind):
        m = self.metrics
        wanted = set(widgetstrip.enabled_widgets(m.config))
        wanted ^= {kind}
        # the strip lays the cards out in the order of the kinds themselves
        m.config["dock_widgets"] = [k for k in widgetstrip.KINDS if k in wanted]
        m.save()
        self.shell.sync_dock_widgets()
        self.redraw()

    # -- visibility ------------------------------------------------------------

    def toggle_visible(self):
        if self.get_visible():
            self.hide()
            self._ensure_tick(False)
            return False
        m = self.metrics
        self._layout()
        self.refresh()
        width, height = self._layout_size()
        self.set_default_size(width, height)
        self.resize(width, height)
        screen = m.width or 1366
        self.set_horizontal_offset(max(0, int((screen - width) / 2)))
        bottom = int(14 * m.scale)
        try:
            bottom += self.shell.dock.shelf_height(m) + 4
        except Exception:
            bottom += 60
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, bottom)
        self.show_all()
        GLib.idle_add(self._after_show)
        self._ensure_tick(True)
        return True

    def _after_show(self):
        self.refresh()
        self.area.queue_draw()
        return False

    # -- painting ----------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        x0, y0, w, h = self._sheet
        draw.glass_panel(cr, x0, y0, w, h, 22 * m.scale, pal,
                         exponent=m.squareness, shadow=True,
                         shadow_spread=16, shadow_alpha=0.34, tint=1.15)
        draw.rounded_path(cr, x0 + 0.5, y0 + 0.5, w - 1, h - 1, 22 * m.scale - 0.5)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.10)
        cr.set_line_width(1.0)
        cr.stroke()
        self._paint_header(cr, m, pal)
        self._paint_rail(cr, m, pal)
        self._paint_previews(cr, m, pal)
        self._paint_close(cr, m, pal)

    def _paint_header(self, cr, m, pal):
        s = m.scale
        x0, y0 = self._sheet[0], self._sheet[1]
        cx = x0 + 16 * s
        glyphs.grid(cr, cx, y0 + 15 * s, 14 * s, pal["text"])
        draw.draw_text(cr, cx + 22 * s, y0 + 22 * s, "Add Widget",
                       15 * s, pal["text"], weight="bold",
                       baseline="middle")
        # the search of the gallery: a quiet field that knows its place
        search_x = x0 + 200 * s + 18 * s
        search_w = self._sheet[2] - (search_x - x0) - 52 * s
        draw.fill_squircle(cr, search_x, y0 + 10 * s, search_w, 24 * s,
                           12 * s, pal["fill_hover"], m.squareness)
        draw.draw_text(cr, search_x + 12 * s, y0 + 22 * s, "Search widgets",
                       10.5 * s, pal["text_faint"], baseline="middle")

    def _paint_rail(self, cr, m, pal):
        s = m.scale
        for _tag, index, x, y, w, h in self.rows:
            _kind, label, glyph = CATEGORIES[index]
            selected = self.category in (CATEGORIES[index][0],)
            if self.category == "all" and index == 0:
                selected = True
            if selected:
                draw.fill_squircle(cr, x, y, w, h, 8 * s,
                                   pal["fill_hover"], m.squareness)
            icon = getattr(glyphs, glyph, None)
            if icon:
                icon(cr, x + 9 * s, y + h / 2 - 7 * s, 14 * s,
                     pal["text"] if selected else pal["text_dim"])
            draw.draw_text(cr, x + 32 * s, y + h / 2, label, 11.5 * s,
                           pal["text"] if selected else pal["text_dim"],
                           baseline="middle")

    def _paint_previews(self, cr, m, pal):
        s = m.scale
        enabled = set(widgetstrip.enabled_widgets(m.config))
        strip_w = {k: int(widgetstrip.WIDTHS[k] * m.scale)
                   for k in widgetstrip.KINDS}
        for hover_index, (tag, kind, cx, cy, cw, chh) in enumerate(self.cells):
            f = min(1.0, (cw - 8 * s) / strip_w[kind])
            card_w, card_h = int(strip_w[kind] * f), int(66 * s * f)
            px = cx + (cw - card_w) / 2
            py = cy + (66 * s - card_h) / 2 - 8 * s
            cr.save()
            cr.translate(px, py)
            cr.scale(f, f)
            widgetstrip.paint_card(kind, self.ctx, cr, 0, 0,
                                   strip_w[kind], int(66 * s), m, pal)
            cr.restore()
            # the red chip of the cards the strip carries already
            if enabled and kind in enabled and hover_index == self.hovered:
                chip = 11 * s
                chipx, chipy = px - chip * 0.4, py - chip * 0.4
                draw.fill_squircle(cr, chipx, chipy, chip * 2, chip * 2,
                                   chip, (0.96, 0.28, 0.25, 1.0), 2.0)
                cr.save()
                cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
                cr.set_line_width(1.8 * s)
                cr.set_line_cap(1)  # round
                cr.move_to(chipx + chip * 0.45, chipy + chip)
                cr.line_to(chipx + chip * 1.55, chipy + chip)
                cr.stroke()
                cr.restore()
            draw.draw_text(cr, cx + cw / 2, cy + 66 * s + 10 * s,
                           widgetstrip.LABELS[kind], 10 * s,
                           pal["text_dim"], weight="bold",
                           align="center", baseline="middle")

    def _paint_close(self, cr, m, pal):
        s = m.scale
        x, y, w, h = self._close
        draw.fill_squircle(cr, x, y, w, h, h / 2, pal["fill_hover"],
                           m.squareness)
        # an X drawn by hand: the shell has no close glyph of its own
        cx, cy = x + w / 2, y + h / 2
        arm = 4.5 * s
        cr.save()
        cr.set_source_rgba(*pal["text_dim"])
        cr.set_line_width(1.6 * s)
        cr.set_line_cap(1)
        for dx, dy in ((1, 1), (1, -1)):
            cr.move_to(cx - arm * dx, cy - arm * dy)
            cr.line_to(cx + arm * dx, cy + arm * dy)
            cr.stroke()
        cr.restore()

    # -- input --------------------------------------------------------------------

    def input_rects(self):
        return [self._sheet]

    def on_motion(self, x, y):
        index = -1
        for i, cell in enumerate(self.cells):
            _t, _k, cx, cy, cw, chh = cell
            if cx <= x <= cx + cw and cy <= y <= cy + chh:
                index = i
                break
        if index != self.hovered:
            self.hovered = index
            self.redraw()

    def on_leave(self):
        if self.hovered != -1:
            self.hovered = -1
            self.redraw()

    def on_click(self, x, y, button):
        cx, cy, cw, chh = self._close
        if cx <= x <= cx + cw and cy <= y <= cy + chh:
            self.toggle_visible()
            return True
        for _tag, index, rx, ry, rw, rh in self.rows:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.category = CATEGORIES[index][0]
                self._layout()
                self.refresh()
                return True
        for _tag, kind, cx, cy, cw, chh in self.cells:
            if cx <= x <= cx + cw and cy <= y <= cy + chh:
                self._toggle_card(kind)
                return True
        return False
