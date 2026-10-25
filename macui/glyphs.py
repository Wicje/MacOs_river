"""Vector glyphs drawn directly in Cairo.

macOS uses SF Symbols everywhere; since those are not redistributable we
draw equivalent shapes ourselves.  Every glyph is authored in a 16x16 unit
box (the Apple logo excepted, which comes from its 24x24 SVG path).
"""

from __future__ import annotations

import math

import cairo

from .svgpath import _APPLE_CMDS, draw_path


def _unit(cr, x, y, size):
    """Return a scale factor for a 16-unit design box."""
    return size / 16.0


def apple(cr, x, y, size, color):
    """The Apple logo, from its original SVG path."""
    scale = size / 24.0
    cr.save()
    cr.set_source_rgba(*color)
    draw_path(cr, _APPLE_CMDS, x, y, scale)
    cr.fill()
    cr.restore()


def spotlight(cr, x, y, size, color):
    """Magnifying glass."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.6 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.arc(x + 6.8 * s, y + 6.8 * s, 4.6 * s, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to(x + 10.3 * s, y + 10.3 * s)
    cr.line_to(x + 14.0 * s, y + 14.0 * s)
    cr.stroke()
    cr.restore()


def control_center(cr, x, y, size, color):
    """Two horizontal sliders -- macOS' Control Center glyph."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.5 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 2 * s, y + 5 * s)
    cr.line_to(x + 14 * s, y + 5 * s)
    cr.move_to(x + 2 * s, y + 11 * s)
    cr.line_to(x + 14 * s, y + 11 * s)
    cr.stroke()
    cr.arc(x + 5.2 * s, y + 5 * s, 2.1 * s, 0, 2 * math.pi)
    cr.fill()
    cr.arc(x + 10.8 * s, y + 11 * s, 2.1 * s, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def wifi(cr, x, y, size, color, level=3):
    """Filled fan of arcs, like the macOS Wi-Fi glyph."""
    s = _unit(cr, x, y, size)
    cx, cy = x + 8 * s, y + 13.6 * s
    cr.save()
    cr.set_source_rgba(*color)
    for i in range(3):
        if i >= level:
            continue
        r_out = (10.0 - i * 3.2) * s
        r_in = r_out - 2.1 * s
        if r_in <= 0:
            continue
        cr.new_sub_path()
        cr.move_to(cx + r_in * math.cos(math.radians(215)),
                   cy + r_in * math.sin(math.radians(215)))
        cr.line_to(cx + r_out * math.cos(math.radians(215)),
                   cy + r_out * math.sin(math.radians(215)))
        cr.arc(cx, cy, r_out, math.radians(215), math.radians(325))
        cr.line_to(cx + r_in * math.cos(math.radians(325)),
                   cy + r_in * math.sin(math.radians(325)))
        cr.arc_negative(cx, cy, r_in, math.radians(325), math.radians(215))
        cr.close_path()
        cr.fill()
    cr.new_sub_path()
    cr.arc(cx, cy - 1.1 * s, 1.5 * s, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def bluetooth(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.5 * s)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to(x + 5.5 * s, y + 3.0 * s)
    cr.line_to(x + 11 * s, y + 8.0 * s)
    cr.line_to(x + 8 * s, y + 13.0 * s)
    cr.line_to(x + 5.5 * s, y + 11.0 * s)
    cr.move_to(x + 5.5 * s, y + 5.0 * s)
    cr.line_to(x + 11 * s, y + 3.0 * s)
    cr.line_to(x + 8 * s, y + 6.0 * s)
    cr.line_to(x + 5.5 * s, y + 5.0 * s)
    cr.stroke()
    cr.restore()


def battery(cr, x, y, size, color, level=0.8, charging=False):
    """Battery outline with a fill level, drawn in a 22x12 unit box."""
    s = size / 12.0
    w, h = 20.0 * s, 10.0 * s
    bx, by = x, y + 1.0 * s
    r = h / 2
    cr.save()
    cr.set_source_rgba(*color)

    def body():
        cr.new_sub_path()
        cr.arc(bx + r, by + r, r, math.pi, 1.5 * math.pi)
        cr.arc(bx + w - r, by + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.arc(bx + w - r, by + h - r, r, 0, 0.5 * math.pi)
        cr.arc(bx + r, by + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()

    body()
    cr.set_line_width(1.1 * s)
    cr.stroke()

    cr.new_sub_path()
    cr.rectangle(bx + w + 0.2 * s, by + h / 2 - 1.7 * s, 1.4 * s, 3.4 * s)
    cr.fill()

    inner = w - 4.0 * s
    fill_w = max(0.0, inner * min(max(level, 0.0), 1.0))
    if fill_w > 0.4 * s:
        cr.save()
        body()
        cr.clip()
        cr.rectangle(bx + 2.0 * s, by, fill_w, h)
        cr.fill()
        cr.restore()

    if charging:
        cr.move_to(x + 10.4 * s, y + 1.2 * s)
        cr.line_to(x + 7.6 * s, y + 7.0 * s)
        cr.line_to(x + 10.2 * s, y + 7.0 * s)
        cr.line_to(x + 8.2 * s, y + 12.6 * s)
        cr.line_to(x + 12.4 * s, y + 6.2 * s)
        cr.line_to(x + 9.8 * s, y + 6.2 * s)
        cr.close_path()
        cr.fill()
    cr.restore()


def chevron_down(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.4 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 4 * s, y + 6.5 * s)
    cr.line_to(x + 8 * s, y + 10 * s)
    cr.line_to(x + 12 * s, y + 6.5 * s)
    cr.stroke()
    cr.restore()


def crescent(cr, cx, cy, r, dx, dy, r2):
    """Fill the crescent formed by circle(r) minus the offset circle(r2).

    The two circles are intersected analytically so the crescent has clean
    tips instead of the lens shape a naive two-arc path produces.
    """
    d = math.hypot(dx, dy)
    if d >= r + r2 or d <= abs(r - r2) or d == 0:
        cr.new_sub_path()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        return
    a = (d * d + r * r - r2 * r2) / (2 * d)
    h = math.sqrt(max(0.0, r * r - a * a))
    ux, uy = dx / d, dy / d
    px, py = cx + a * ux, cy + a * uy
    ix1, iy1 = px - h * uy, py + h * ux
    ix2, iy2 = px + h * uy, py - h * ux
    t1 = math.atan2(iy1 - cy, ix1 - cx)
    t2 = math.atan2(iy2 - cy, ix2 - cx)
    cr.new_sub_path()
    cr.move_to(ix1, iy1)
    # outer arc, the side away from the biting circle
    if math.atan2(uy, ux) > 0:
        cr.arc_negative(cx, cy, r, t1, t2)
    else:
        cr.arc(cx, cy, r, t1, t2)
    s1 = math.atan2(iy2 - (cy + dy), ix2 - (cx + dx))
    s2 = math.atan2(iy1 - (cy + dy), ix1 - (cx + dx))
    cr.arc_negative(cx + dx, cy + dy, r2, s1, s2)
    cr.close_path()


def moon(cr, x, y, size, color):
    """Crescent -- the macOS Focus glyph."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    crescent(cr, x + 7.4 * s, y + 8.6 * s, 6.2 * s, 2.6 * s, -0.8 * s, 5.9 * s)
    cr.fill()
    cr.restore()


def display(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.5 * s)
    cr.rectangle(x + 1.5 * s, y + 2.5 * s, 13 * s, 8.5 * s)
    cr.stroke()
    cr.move_to(x + 5.5 * s, y + 13.5 * s)
    cr.line_to(x + 10.5 * s, y + 13.5 * s)
    cr.stroke()
    cr.restore()


def speaker(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.move_to(x + 2 * s, y + 6 * s)
    cr.line_to(x + 4.6 * s, y + 6 * s)
    cr.line_to(x + 7.6 * s, y + 3 * s)
    cr.line_to(x + 7.6 * s, y + 13 * s)
    cr.line_to(x + 4.6 * s, y + 10 * s)
    cr.line_to(x + 2 * s, y + 10 * s)
    cr.close_path()
    cr.fill()
    cr.set_line_width(1.3 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.arc(x + 7.6 * s, y + 8 * s, 3.6 * s, -math.radians(50), math.radians(50))
    cr.stroke()
    cr.restore()


def airplay(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.5 * s)
    cr.rectangle(x + 1.5 * s, y + 3 * s, 13 * s, 7.5 * s)
    cr.stroke()
    cr.move_to(x + 8 * s, y + 12 * s)
    cr.line_to(x + 5.4 * s, y + 14.4 * s)
    cr.line_to(x + 10.6 * s, y + 14.4 * s)
    cr.close_path()
    cr.fill()
    cr.restore()


def accessibility(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.arc(x + 8 * s, y + 4.2 * s, 1.9 * s, 0, 2 * math.pi)
    cr.fill()
    cr.set_line_width(1.6 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 8 * s, y + 6.6 * s)
    cr.line_to(x + 8 * s, y + 11 * s)
    cr.move_to(x + 4.4 * s, y + 8.2 * s)
    cr.line_to(x + 11.6 * s, y + 8.2 * s)
    cr.move_to(x + 8 * s, y + 11 * s)
    cr.line_to(x + 5.6 * s, y + 14.4 * s)
    cr.move_to(x + 8 * s, y + 11 * s)
    cr.line_to(x + 10.4 * s, y + 14.4 * s)
    cr.stroke()
    cr.restore()


def grid(cr, x, y, size, color):
    """Four rounded squares -- the Launchpad / Applications glyph."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    for gx in (2.5, 8.5):
        for gy in (2.5, 8.5):
            cr.rectangle(x + gx * s, y + gy * s, 5 * s, 5 * s)
    cr.fill()
    cr.restore()


def check(cr, x, y, size, color):
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.7 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to(x + 3.5 * s, y + 8.5 * s)
    cr.line_to(x + 6.4 * s, y + 11.4 * s)
    cr.line_to(x + 12.5 * s, y + 4.6 * s)
    cr.stroke()
    cr.restore()


def clipboard(cr, x, y, size, color):
    """The SF Symbols clipboard: a board, a tab on top and two text lines."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    r = 1.6 * s
    bx0, bx1 = x + 3.0 * s, x + 13.0 * s
    by0, by1 = y + 2.6 * s, y + 14.0 * s
    cr.set_line_width(1.4 * s)
    # the board with rounded corners
    cr.move_to(bx0 + r, by0)
    cr.line_to(bx1 - r, by0)
    cr.arc(bx1 - r, by0 + r, r, -math.pi / 2, 0)
    cr.line_to(bx1, by1 - r)
    cr.arc(bx1 - r, by1 - r, r, 0, math.pi / 2)
    cr.line_to(bx0 + r, by1)
    cr.arc(bx0 + r, by1 - r, r, math.pi / 2, math.pi)
    cr.line_to(bx0, by0 + r)
    cr.arc(bx0 + r, by0 + r, r, math.pi, 3 * math.pi / 2)
    cr.stroke()
    # the clip tab that grips the top edge
    tab_w = 4.6 * s
    cr.move_to(x + 8 * s - tab_w / 2, by0 + 0.7 * s)
    cr.line_to(x + 8 * s - tab_w / 2, y + 3.6 * s)
    cr.arc(x + 8 * s, y + 3.6 * s, tab_w / 2, math.pi, 0)
    cr.line_to(x + 8 * s + tab_w / 2, by0 + 0.7 * s)
    cr.stroke()
    # the two lines of the copied text
    cr.move_to(x + 5.8 * s, y + 7.4 * s)
    cr.line_to(x + 10.2 * s, y + 7.4 * s)
    cr.stroke()
    cr.move_to(x + 5.8 * s, y + 10.2 * s)
    cr.line_to(x + 10.2 * s, y + 10.2 * s)
    cr.stroke()
    cr.restore()


def camera(cr, x, y, size, color):
    """The SF Symbols camera: a soft body over a ringed lens."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.4 * s)
    r = 2.2 * s
    bx0, bx1 = x + 1.5 * s, x + 14.5 * s
    by0, by1 = y + 4.5 * s, y + 13.5 * s
    # the body: rounded, with the viewfinder bump on the top edge
    cr.move_to(bx0 + r, by0)
    cr.line_to(bx1 - r, by0)
    cr.arc(bx1 - r, by0 + r, r, -math.pi / 2, 0)
    cr.line_to(bx1, by1 - r)
    cr.arc(bx1 - r, by1 - r, r, 0, math.pi / 2)
    cr.line_to(bx0 + r, by1)
    cr.arc(bx0 + r, by1 - r, r, math.pi / 2, math.pi)
    cr.line_to(bx0, by0 + r)
    cr.arc(bx0 + r, by0 + r, r, math.pi, 3 * math.pi / 2)
    cr.stroke()
    # the bump of the viewfinder
    cr.move_to(x + 5.4 * s, by0)
    cr.line_to(x + 6.2 * s, y + 2.4 * s)
    cr.arc(x + 8 * s, y + 2.4 * s, 1.8 * s, math.pi, 0)
    cr.line_to(x + 9.8 * s, by0)
    cr.stroke()
    # the lens: a ring, filled heart, like SF's camera
    cr.arc(x + 8 * s, y + 9.0 * s, 2.5 * s, 0, 2 * math.pi)
    cr.stroke()
    cr.arc(x + 8 * s, y + 9.0 * s, 1.0 * s, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def sun(cr, x, y, size, color):
    """A sun, for the display settings."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.arc(x + 8 * s, y + 8 * s, 3.4 * s, 0, 2 * math.pi)
    cr.fill()
    cr.set_line_width(1.3 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for index in range(8):
        angle = index * math.pi / 4
        cr.move_to(x + 8 * s + math.cos(angle) * 5.2 * s,
                   y + 8 * s + math.sin(angle) * 5.2 * s)
        cr.line_to(x + 8 * s + math.cos(angle) * 6.8 * s,
                   y + 8 * s + math.sin(angle) * 6.8 * s)
    cr.stroke()
    cr.restore()


def power(cr, x, y, size, color):
    """The power symbol."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.6 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.arc(x + 8 * s, y + 8.6 * s, 5.4 * s, math.radians(-60),
           math.radians(240))
    cr.stroke()
    cr.move_to(x + 8 * s, y + 1.6 * s)
    cr.line_to(x + 8 * s, y + 6.4 * s)
    cr.stroke()
    cr.restore()


def energy(cr, x, y, size, color, mode="balanced"):
    """The power profile of the system, as the menu bar status tells it:
    the bolt for performance, the half gauge for balanced, the little
    battery for saving."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    if mode == "performance":
        cr.move_to(x + 9.6 * s, y + 0.8 * s)
        cr.line_to(x + 3.4 * s, y + 9.2 * s)
        cr.line_to(x + 7.6 * s, y + 9.2 * s)
        cr.line_to(x + 6.4 * s, y + 15.2 * s)
        cr.line_to(x + 12.6 * s, y + 6.8 * s)
        cr.line_to(x + 8.4 * s, y + 6.8 * s)
        cr.close_path()
        cr.fill()
    elif mode == "power-saver":
        battery(cr, x + 1 * s, y + 3.4 * s, size * 0.62, color, level=0.15)
    else:
        cx, cy, r = x + 8 * s, y + 8 * s, 6.2 * s
        cr.set_line_width(1.5 * s)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.new_sub_path()
        cr.move_to(cx, cy)
        cr.arc(cx, cy, r, -0.5 * math.pi, 0.5 * math.pi)
        cr.close_path()
        cr.fill()
    cr.restore()


def lock(cr, x, y, size, color):
    """A padlock."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.4 * s)
    cr.arc(x + 8 * s, y + 6.6 * s, 3.4 * s, math.pi, 2 * math.pi)
    cr.stroke()
    cr.rectangle(x + 3.4 * s, y + 6.6 * s, 9.2 * s, 7 * s)
    cr.fill()
    cr.restore()


def display_brightness(cr, x, y, size, color):
    """A sun over a rectangle, the display brightness symbol."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.3 * s)
    cr.rectangle(x + 1.5 * s, y + 8.5 * s, 13 * s, 6 * s)
    cr.stroke()
    cr.arc(x + 8 * s, y + 5 * s, 2.4 * s, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def sparkles(cr, x, y, size, color):
    """The sparkle of the Writing Tools."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)

    def star(cx, cy, r):
        cr.move_to(cx, cy - r)
        cr.curve_to(cx + r * 0.06, cy - r * 0.20, cx + r * 0.20, cy - r * 0.06,
                    cx + r, cy)
        cr.curve_to(cx + r * 0.20, cy + r * 0.06, cx + r * 0.06, cy + r * 0.20,
                    cx, cy + r)
        cr.curve_to(cx - r * 0.06, cy + r * 0.20, cx - r * 0.20, cy + r * 0.06,
                    cx - r, cy)
        cr.curve_to(cx - r * 0.20, cy - r * 0.06, cx - r * 0.06, cy - r * 0.20,
                    cx, cy - r)
        cr.close_path()

    star(x + 5.4 * s, y + 5.4 * s, 5.0 * s)
    cr.fill()
    star(x + 12.2 * s, y + 11.6 * s, 2.8 * s)
    cr.fill()
    cr.restore()


def wand(cr, x, y, size, color):
    """The magic wand of the assistant."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.6 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 3.4 * s, y + 12.6 * s)
    cr.line_to(x + 10.4 * s, y + 5.6 * s)
    cr.stroke()
    cr.move_to(x + 4.6 * s, y + 5.0 * s)
    cr.line_to(x + 7.4 * s, y + 5.0 * s)
    cr.move_to(x + 6.0 * s, y + 3.6 * s)
    cr.line_to(x + 6.0 * s, y + 6.4 * s)
    cr.stroke()
    cr.restore()


def microphone(cr, x, y, size, color):
    """The microphone of the dictation, drawn like the SF Symbols mic."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    # the solid capsule of SF Symbols' mic.fill
    cr.move_to(x + 5.6 * s, y + 4.6 * s)
    cr.arc(x + 8 * s, y + 4.6 * s, 2.4 * s, math.pi, 0)
    cr.line_to(x + 10.4 * s, y + 7.2 * s)
    cr.arc(x + 8 * s, y + 7.2 * s, 2.4 * s, 0, math.pi)
    cr.close_path()
    cr.fill()
    # the U bracket around it, the stand and the base
    cr.set_line_width(1.4 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 4.4 * s, y + 7.4 * s)
    cr.arc(x + 8 * s, y + 7.4 * s, 3.6 * s, 0, math.pi)
    cr.stroke()
    cr.move_to(x + 8 * s, y + 11.0 * s)
    cr.line_to(x + 8 * s, y + 13.0 * s)
    cr.stroke()
    cr.move_to(x + 5.8 * s, y + 13.0 * s)
    cr.line_to(x + 10.2 * s, y + 13.0 * s)
    cr.stroke()
    cr.restore()


def bell(cr, x, y, size, color):
    """A notification bell, for the settings sidebar."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.4 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    # the body: a dome from the left shoulder over the top to the right,
    # straight down to the skirt
    cr.move_to(x + 4.4 * s, y + 11.2 * s)
    cr.arc(x + 8 * s, y + 8.2 * s, 3.6 * s, math.pi, 2 * math.pi)
    cr.line_to(x + 11.6 * s, y + 11.2 * s)
    cr.stroke()
    # the skirt bar
    cr.move_to(x + 3.2 * s, y + 11.2 * s)
    cr.line_to(x + 12.8 * s, y + 11.2 * s)
    cr.stroke()
    # the clapper
    cr.arc(x + 8 * s, y + 13.2 * s, 1.0 * s, 0, math.pi)
    cr.stroke()
    cr.restore()


def keyboard(cr, x, y, size, color):
    """A keyboard, for the settings sidebar."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.3 * s)
    r = 1.6 * s
    x0, x1 = x + 1.4 * s, x + 14.6 * s
    y0, y1 = y + 3.8 * s, y + 12.2 * s
    cr.move_to(x0 + r, y0)
    cr.line_to(x1 - r, y0)
    cr.arc(x1 - r, y0 + r, r, -math.pi / 2, 0)
    cr.line_to(x1, y1 - r)
    cr.arc(x1 - r, y1 - r, r, 0, math.pi / 2)
    cr.line_to(x0 + r, y1)
    cr.arc(x0 + r, y1 - r, r, math.pi / 2, math.pi)
    cr.line_to(x0, y0 + r)
    cr.arc(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2)
    cr.stroke()
    for row, cy in ((0, y + 6.4 * s), (1, y + 9.0 * s)):
        for col in range(4):
            cr.arc(x + (3.4 + col * 2.4 + row * 1.2) * s, cy, 0.65 * s,
                   0, 2 * math.pi)
            cr.fill()
    cr.restore()


def phone(cr, x, y, size, color):
    """A phone, for the phone hub."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.4 * s)
    r = 1.8 * s
    x0, x1 = x + 4.8 * s, x + 11.2 * s
    y0, y1 = y + 1.6 * s, y + 14.4 * s
    cr.move_to(x0 + r, y0)
    cr.line_to(x1 - r, y0)
    cr.arc(x1 - r, y0 + r, r, -math.pi / 2, 0)
    cr.line_to(x1, y1 - r)
    cr.arc(x1 - r, y1 - r, r, 0, math.pi / 2)
    cr.line_to(x0 + r, y1)
    cr.arc(x0 + r, y1 - r, r, math.pi / 2, math.pi)
    cr.line_to(x0, y0 + r)
    cr.arc(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2)
    cr.stroke()
    # the home dot, and the two arrows of the clipboard moving both ways
    cr.set_line_width(1.2 * s)
    cr.arc(x + 8 * s, y + 12.6 * s, 0.55 * s, 0, 2 * math.pi)
    cr.fill()
    cr.move_to(x + 6.6 * s, y + 9.0 * s)
    cr.line_to(x + 6.6 * s, y + 6.4 * s)
    cr.move_to(x + 5.7 * s, y + 7.3 * s)
    cr.line_to(x + 6.6 * s, y + 6.4 * s)
    cr.line_to(x + 7.5 * s, y + 7.3 * s)
    cr.stroke()
    cr.move_to(x + 9.4 * s, y + 7.0 * s)
    cr.line_to(x + 9.4 * s, y + 9.6 * s)
    cr.move_to(x + 8.5 * s, y + 8.7 * s)
    cr.line_to(x + 9.4 * s, y + 9.6 * s)
    cr.line_to(x + 10.3 * s, y + 8.7 * s)
    cr.stroke()
    cr.restore()


def shuffle(cr, x, y, size, color):
    """The crossed arrows of the shuffle button."""
    s = _unit(cr, x, y, size)
    cr.save()
    cr.set_source_rgba(*color)
    cr.set_line_width(1.3 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x + 2.0 * s, y + 4.0 * s)
    cr.line_to(x + 4.6 * s, y + 4.0 * s)
    cr.line_to(x + 12.0 * s, y + 12.0 * s)
    cr.line_to(x + 14.0 * s, y + 12.0 * s)
    cr.stroke()
    cr.move_to(x + 2.0 * s, y + 12.0 * s)
    cr.line_to(x + 4.6 * s, y + 12.0 * s)
    cr.line_to(x + 12.0 * s, y + 4.0 * s)
    cr.line_to(x + 14.0 * s, y + 4.0 * s)
    cr.stroke()
    # the arrow heads
    cr.move_to(x + 11.6 * s, y + 4.0 * s)
    cr.line_to(x + 14.4 * s, y + 4.0 * s)
    cr.line_to(x + 14.4 * s, y + 6.6 * s)
    cr.move_to(x + 11.6 * s, y + 12.0 * s)
    cr.line_to(x + 14.4 * s, y + 12.0 * s)
    cr.line_to(x + 14.4 * s, y + 9.4 * s)
    cr.stroke()
    cr.restore()


def star(cr, x, y, size, color):
    """The favourite star."""
    s = _unit(cr, x, y, size)
    cx, cy = x + 8 * s, y + 8 * s
    outer, inner = 7.0 * s, 3.0 * s
    cr.save()
    cr.set_source_rgba(*color)
    for index in range(10):
        angle = math.pi / 2 + index * math.pi / 5
        radius = outer if index % 2 == 0 else inner
        px = cx + math.cos(angle) * radius
        py = cy - math.sin(angle) * radius
        if index == 0:
            cr.move_to(px, py)
        else:
            cr.line_to(px, py)
    cr.close_path()
    cr.fill()
    cr.restore()
