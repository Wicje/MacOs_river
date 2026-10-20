"""Minimal SVG path parsing so we can reuse real vector artwork in Cairo.

Only the commands that appear in icon paths are supported: M/m L/l H/h V/v
C/c S/s Q/q T/t Z/z.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def parse_path(d):
    """Return a list of (command, [numbers]) tuples."""
    out = []
    for match in _TOKEN.finditer(d):
        if match.group(1):
            out.append((match.group(1), []))
        elif out:
            out[-1][1].append(float(match.group(2)))
    return out


def draw_path(cr, commands, ox=0.0, oy=0.0, scale=1.0):
    """Replay parsed path commands onto a Cairo context."""
    cr.new_path()
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    last_ctrl = None

    for cmd, nums in commands:
        if cmd in "Mm":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                if cmd == "m":
                    x += cur[0]
                    y += cur[1]
                cur = (x, y)
                if i == 0:
                    start = cur
                    cr.move_to(ox + x * scale, oy + y * scale)
                else:
                    cr.line_to(ox + x * scale, oy + y * scale)
        elif cmd in "Ll":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                if cmd == "l":
                    x += cur[0]
                    y += cur[1]
                cur = (x, y)
                cr.line_to(ox + x * scale, oy + y * scale)
        elif cmd in "Hh":
            for value in nums:
                x = value if cmd == "H" else cur[0] + value
                cur = (x, cur[1])
                cr.line_to(ox + x * scale, oy + cur[1] * scale)
        elif cmd in "Vv":
            for value in nums:
                y = value if cmd == "V" else cur[1] + value
                cur = (cur[0], y)
                cr.line_to(ox + cur[0] * scale, oy + y * scale)
        elif cmd in "Cc":
            for i in range(0, len(nums) - 5, 6):
                x1, y1, x2, y2, x, y = nums[i:i + 6]
                if cmd == "c":
                    x1 += cur[0]; y1 += cur[1]
                    x2 += cur[0]; y2 += cur[1]
                    x += cur[0]; y += cur[1]
                cr.curve_to(ox + x1 * scale, oy + y1 * scale,
                            ox + x2 * scale, oy + y2 * scale,
                            ox + x * scale, oy + y * scale)
                last_ctrl = (x2, y2)
                cur = (x, y)
        elif cmd in "Ss":
            for i in range(0, len(nums) - 3, 4):
                x2, y2, x, y = nums[i:i + 4]
                if cmd == "s":
                    x2 += cur[0]; y2 += cur[1]
                    x += cur[0]; y += cur[1]
                x1, y1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) \
                    if last_ctrl else cur
                cr.curve_to(ox + x1 * scale, oy + y1 * scale,
                            ox + x2 * scale, oy + y2 * scale,
                            ox + x * scale, oy + y * scale)
                last_ctrl = (x2, y2)
                cur = (x, y)
        elif cmd in "Qq":
            for i in range(0, len(nums) - 3, 4):
                x1, y1, x, y = nums[i:i + 4]
                if cmd == "q":
                    x1 += cur[0]; y1 += cur[1]
                    x += cur[0]; y += cur[1]
                cr.curve_to(ox + (cur[0] + 2 * (x1 - cur[0]) / 3) * scale,
                            oy + (cur[1] + 2 * (y1 - cur[1]) / 3) * scale,
                            ox + (x + 2 * (x1 - x) / 3) * scale,
                            oy + (y + 2 * (y1 - y) / 3) * scale,
                            ox + x * scale, oy + y * scale)
                cur = (x, y)
        elif cmd in "Tt":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                if cmd == "t":
                    x += cur[0]; y += cur[1]
                cr.curve_to(ox + (cur[0] + 2 * (0 - cur[0]) / 3) * scale,
                            oy + (cur[1] + 2 * (0 - cur[1]) / 3) * scale,
                            ox + (x + 2 * (0 - x) / 3) * scale,
                            oy + (y + 2 * (0 - y) / 3) * scale,
                            ox + x * scale, oy + y * scale)
                cur = (x, y)
        elif cmd in "Zz":
            cr.close_path()
            cur = start
    return cur


APPLE_PATH = (
    "M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014"
    "-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065"
    "2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948"
    "1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04"
    "2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09"
    "-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805"
    "-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701"
)

_APPLE_CMDS = parse_path(APPLE_PATH)
