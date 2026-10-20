"""Cairo drawing primitives for the macOS Tahoe shell.

Everything the shell renders -- glass panels, squircle icons, spec edges,
soft shadows, text -- is drawn here with pycairo so every pixel is under
our control.  Text goes through PangoCairo so SF Pro is shaped and hinted
properly instead of using Cairo's toy text API.
"""

from __future__ import annotations

import math
import os

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gdk, GdkPixbuf, Pango, PangoCairo  # noqa: E402

ICON_DIR = os.path.expanduser("~/.local/share/macshell/icons")

_pixbuf_cache: dict[str, GdkPixbuf.Pixbuf] = {}


# --- paths -----------------------------------------------------------------

def squircle_path(cr, x, y, w, h, radius, exponent=5.0, segments=14):
    """Append a superellipse-cornered rectangle to the current path.

    Apple's continuous corners are a superellipse with exponent ~5, not a
    circular arc; the difference is very visible at large radii.

    The shape is walked clockwise: top edge, right, bottom, left.  Every
    corner runs from a larger to a smaller angle so the straight edges
    between them stay straight.
    """
    r = min(radius, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return

    p = 2.0 / exponent

    def corner(cx, cy, t0, t1, first=False):
        for i in range(segments + 1):
            t = t0 + (t1 - t0) * i / segments
            c, s = math.cos(t), math.sin(t)
            px = cx + r * math.copysign(abs(c) ** p, c)
            py = cy + r * math.copysign(abs(s) ** p, s)
            if i == 0 and first:
                cr.move_to(px, py)
            else:
                cr.line_to(px, py)

    cr.new_sub_path()
    corner(x + r, y + r, 1.5 * math.pi, math.pi, first=True)   # top-left
    cr.line_to(x, y + h - r)
    corner(x + r, y + h - r, math.pi, 0.5 * math.pi)           # bottom-left
    cr.line_to(x + w - r, y + h)
    corner(x + w - r, y + h - r, 0.5 * math.pi, 0.0)           # bottom-right
    cr.line_to(x + w, y + r)
    corner(x + w - r, y + r, 0.0, -0.5 * math.pi)              # top-right
    cr.close_path()


def rounded_path(cr, x, y, w, h, radius):
    """Plain circular rounded rectangle."""
    r = min(radius, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


# --- glass material --------------------------------------------------------

def soft_shadow(cr, path_fn, spread, alpha, offset=(0, 4), passes=16,
                bounds=None):
    """Approximate a blurred drop shadow by stroking the path repeatedly.

    Cairo has no blur filter, so we fake the falloff with concentric
    strokes of decreasing width and increasing opacity.  The shape itself
    is clipped away first: a stroke covers half its width inside the path,
    which would otherwise darken the panel instead of casting a shadow.
    """
    cr.save()
    if bounds is not None:
        bx, by, bw, bh = bounds
        pad = spread + abs(offset[0]) + 4
        cr.rectangle(bx - pad, by - pad, bw + pad * 2, bh + pad * 2)
        path_fn(cr)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.clip()
    cr.translate(offset[0], offset[1])
    for i in range(passes):
        t = 1.0 - (i + 1) / passes
        cr.new_path()
        path_fn(cr)
        cr.set_line_width(2 * spread * t)
        cr.set_source_rgba(0, 0, 0, alpha * (1 - t) ** 2)
        cr.stroke()
    cr.restore()


def glass_panel(cr, x, y, w, h, radius, palette, *,
                exponent=5.0, shadow=True, tint=1.0, shadow_spread=14,
                shadow_alpha=None, edge=True):
    """Draw a Liquid Glass panel: soft shadow, translucent body, spec edge."""
    path_fn = lambda c: squircle_path(c, x, y, w, h, radius, exponent)

    if shadow:
        a = palette["shadow"][3] if shadow_alpha is None else shadow_alpha
        soft_shadow(cr, path_fn, shadow_spread, a, bounds=(x, y, w, h))

    # body: vertical gradient of the glass tint
    cr.save()
    path_fn(cr)
    cr.clip()
    grad = cairo.LinearGradient(0, y, 0, y + h)
    top = palette["glass_top"]
    bot = palette["glass_bottom"]
    grad.add_color_stop_rgba(0.0, top[0], top[1], top[2], top[3] * tint)
    grad.add_color_stop_rgba(1.0, bot[0], bot[1], bot[2], bot[3] * tint)
    cr.set_source(grad)
    cr.rectangle(x, y, w, h)
    cr.fill()
    cr.restore()

    # specular edge: bright along the top, fading toward the bottom
    if edge:
        cr.save()
        path_fn(cr)
        cr.clip()
        stroke = cairo.LinearGradient(0, y, 0, y + h)
        et = palette["glass_edge_top"]
        eb = palette["glass_edge_bottom"]
        stroke.add_color_stop_rgba(0.0, et[0], et[1], et[2], et[3])
        stroke.add_color_stop_rgba(1.0, eb[0], eb[1], eb[2], eb[3])
        cr.set_source(stroke)
        cr.set_line_width(1.0)
        path_fn(cr)
        cr.stroke()
        cr.restore()


def fill_squircle(cr, x, y, w, h, radius, color, exponent=5.0):
    cr.save()
    squircle_path(cr, x, y, w, h, radius, exponent)
    cr.set_source_rgba(*color)
    cr.fill()
    cr.restore()


def stroke_squircle(cr, x, y, w, h, radius, color, width=1.0, exponent=5.0):
    cr.save()
    squircle_path(cr, x, y, w, h, radius, exponent)
    cr.set_source_rgba(*color)
    cr.set_line_width(width)
    cr.stroke()
    cr.restore()


# --- text ------------------------------------------------------------------

def _font_desc(size, weight="normal", family="SF Pro Text", style="normal"):
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_absolute_size(size * Pango.SCALE)
    desc.set_weight(getattr(Pango.Weight, weight.upper(), Pango.Weight.NORMAL))
    desc.set_style(getattr(Pango.Style, style.upper(), Pango.Style.NORMAL))
    return desc


def text_width(cr, text, size, weight="normal", family="SF Pro Text"):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font_desc(size, weight, family))
    layout.set_text(text)
    return layout.get_pixel_size()[0]


def draw_text(cr, x, y, text, size, color, *, weight="normal",
              family="SF Pro Text", align="left", max_width=None,
              ellipsize=False, baseline="top"):
    """Draw a single line of text.  Returns the layout width in pixels."""
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font_desc(size, weight, family))
    layout.set_text(text)

    if max_width is not None:
        layout.set_width(max_width * Pango.SCALE)
        if ellipsize:
            layout.set_ellipsize(Pango.EllipsizeMode.END)

    lw, lh = layout.get_pixel_size()
    px = x
    if align == "center":
        px = x - lw / 2
    elif align == "right":
        px = x - lw
    py = y
    if baseline == "middle":
        py = y - lh / 2
    elif baseline == "bottom":
        py = y - lh

    cr.save()
    cr.set_source_rgba(*color)
    cr.move_to(px, py)
    PangoCairo.show_layout(cr, layout)
    cr.restore()
    return lw


# --- icons -----------------------------------------------------------------

def load_pixbuf(name):
    """Load a dock icon from the asset directory (cached)."""
    if name in _pixbuf_cache:
        return _pixbuf_cache[name]
    path = os.path.join(ICON_DIR, name if name.endswith(".png") else name + ".png")
    if not os.path.exists(path):
        return None
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
    except Exception:
        return None
    _pixbuf_cache[name] = pb
    return pb


def draw_icon(cr, name, x, y, size):
    """Draw an app icon scaled to `size` with its top-left at (x, y)."""
    pb = load_pixbuf(name)
    if pb is None:
        return False
    w, h = pb.get_width(), pb.get_height()
    scale = size / max(w, h)
    dw, dh = w * scale, h * scale
    cr.save()
    cr.translate(x + (size - dw) / 2, y + (size - dh) / 2)
    cr.scale(dw / w, dh / h)
    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
    cr.paint()
    cr.restore()
    return True


def icon_size(name, fallback=48):
    pb = load_pixbuf(name)
    return fallback if pb is None else max(pb.get_width(), pb.get_height())
