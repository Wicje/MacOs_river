"""The macOS menu bar.

A full-width translucent strip across the top of every workspace: the Apple
logo, the focused application's name, the standard application menus and
the status cluster on the right (Spotlight, Control Centre, Wi-Fi, battery
and the clock).
"""

from __future__ import annotations

import math
import os
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib  # noqa: E402

from ..macui import actions, draw, glyphs, menus, metrics as _metrics, state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

def battery_level():
    for name in ("BAT0", "BAT1"):
        path = f"/sys/class/power_supply/{name}/capacity"
        try:
            with open(path) as fh:
                return int(fh.read().strip())
        except (OSError, ValueError):
            continue
    return None


class MenuBar(Panel):
    NAMESPACE = "mac-menubar"

    def __init__(self, metrics, shell):
        height = int(metrics.px("menu_bar_height"))
        super().__init__(
            metrics,
            layer="top",
            anchors={"top": True, "left": True, "right": True},
            exclusive=height,
        )
        self.shell = shell
        self.set_content_size(-1, height)
        self.bar_height = height
        self._items: list = []
        self._pulse_id = None
        self._app_name = "Finder"
        self._app_id = ""
        self._battery = None
        self._charging = False
        self._media = None
        self._focused = ""

    # -- state ---------------------------------------------------------------

    def refresh(self):
        self._app_id = state.focused_app_id()
        self._app_name = state.focused_app() or "Finder"
        self._media = state.now_playing()
        self._focused = state.focused_window()
        self._battery = battery_level()
        try:
            with open("/sys/class/power_supply/BAT0/status") as fh:
                self._charging = "Charging" in fh.read()
        except OSError:
            self._charging = False
        # the badges read once a second; the pulse loop only exists while
        # one of them wants to breathe
        self._status_items_cache = state.status_items()
        pulsing = any(st.get("pulse") for st in self._status_items_cache)
        if pulsing and not self._pulse_id:
            self._pulse_id = GLib.timeout_add(66, self._pulse_tick)
        elif not pulsing and self._pulse_id:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = None
        self.redraw()

    # -- painting ------------------------------------------------------------

    def paint(self, cr, width, height):
        m = self.metrics
        pal = m.palette()
        s = m.scale

        bar = self.bar_height
        # translucent material so the compositor blur reads through
        cr.set_source_rgba(*pal["menu_bar"])
        cr.rectangle(0, 0, width, bar)
        cr.fill()
        cr.set_source_rgba(*pal["separator"])
        cr.rectangle(0, bar - 1, width, 1)
        cr.fill()

        pad = m.px("menu_pad_x")
        gap = m.px("menu_item_gap")
        font = m.font("menu_font_size")
        icon = m.px("apple_logo")

        self._items = []

        # Apple logo
        glyphs.apple(cr, pad, (bar - icon) / 2, icon, pal["text"])
        x = pad + icon + gap
        self._items.append({"name": "__apple__", "x": pad, "w": icon + gap})

        # focused application name (bold)
        name_w = draw.text_width(cr, self._app_name, font, "bold")
        draw.draw_text(cr, x, bar / 2, self._app_name, font, pal["text"],
                       weight="bold", baseline="middle")
        x += name_w + gap * 1.4
        self._items.append({"name": "__app__", "x": x, "w": name_w})

        # application menus, the ones the focused application would have
        for title, _items in menus.menus_for(self._app_id):
            w = draw.text_width(cr, title, font)
            draw.draw_text(cr, x, bar / 2, title, font, pal["text"],
                           baseline="middle")
            self._items.append({"name": title, "x": x, "w": w})
            x += w + gap

        # status cluster, right aligned
        right = width - pad
        glyph = m.px("status_glyph")

        clock_text = time.strftime("%a %-d %b  %H:%M")
        if self._battery is not None:
            clock_text = f"{self._battery}%  " + clock_text
        clock_w = draw.text_width(cr, clock_text, m.font("clock_font_size"))
        draw.draw_text(cr, right, bar / 2, clock_text, m.font("clock_font_size"),
                       pal["text"], align="right", baseline="middle")
        self._clock_x = right - clock_w
        self._clock_w = clock_w
        right -= clock_w + m.px("status_gap")

        if self._battery is not None:
            bh = 11 * s
            bw = 22 * s
            glyphs.battery(cr, right - bw, (bar - bh) / 2, bh,
                           pal["text"], self._battery / 100.0, self._charging)
            self._battery_x = right - bw
            self._battery_w = bw
            right -= bw + m.px("status_gap")

        # the microphone, the way macOS tucks a privacy indicator into the
        # status cluster: far while nobody listens, the warm orange of the
        # notch light while a program records.  A click toggles the
        # dictation.
        live = state.mic_active()
        mic_color = ((1.0, 0.58, 0.0, 1.0) if live else (*pal["text_faint"],))
        glyphs.microphone(cr, right - glyph, (bar - glyph) / 2, glyph,
                          mic_color)
        self._mic_x = right - glyph
        right -= glyph + m.px("status_gap")

        # the power profile, the way the Control Centre lists it
        self._power = state.power_mode()
        glyphs.energy(cr, right - glyph - 2 * s, (bar - glyph) / 2, glyph,
                      pal["text"], self._power)
        self._profile_x = right - glyph - 2 * s
        right -= glyph + 2 * s + m.px("status_gap")

        wifi_on = state.wifi_enabled()
        wifi_color = pal["text"] if wifi_on else pal["text_faint"]
        glyphs.wifi(cr, right - glyph, (bar - glyph) / 2, glyph, wifi_color,
                    level=3)
        self._wifi_x = right - glyph
        right -= glyph + m.px("status_gap")

        glyphs.control_center(cr, right - glyph, (bar - glyph) / 2, glyph, pal["text"])
        self._cc_x = right - glyph
        right -= glyph + m.px("status_gap")

        glyphs.spotlight(cr, right - glyph, (bar - glyph) / 2, glyph, pal["text"])
        self._spotlight_x = right - glyph
        right -= glyph + m.px("status_gap")

        # the menu bar extras, the programs of the tray: macOS tucks them
        # in front of the system status icons, so they sit on this side
        self._tray_x = []
        tray = getattr(self.shell, "tray", None)
        if tray is not None:
            from gi.repository import Gdk as _Gdk
            for item in tray.order():
                height = m.px("status_glyph")
                pixbuf = item.pixbuf(height)
                if pixbuf is None:
                    continue
                iw = pixbuf.get_width()
                ih = pixbuf.get_height()
                factor = height / max(iw, ih)
                dw = iw * factor
                dh = ih * factor
                cr.save()
                cr.translate(right - dw, (bar - dh) / 2)
                cr.scale(dw / iw, dh / ih)
                _Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
                if dw < 2:
                    continue
                self._tray_x.append((right - dw, dw, item))
                right -= dw + m.px("status_gap") * 0.7

        # the status items of the programs -- NSStatusItem, the macOS
        # menu bar row handed over to the machine: any program can sit
        # here with a glyph or its own icon, a tint, a small count and
        # the command a click runs.  Published through the mstatus
        # helper as tiny json files with their own expiry, so a program
        # that stops beating fades out of the bar on its own.
        self._status_hits = []
        font2 = m.font("clock_font_size")
        items = getattr(self, "_status_items_cache", None)
        if items is None:
            items = state.status_items()
        for st in items:
            color = self._color_of(st, pal)
            if st.get("pulse"):
                # an active program: the badge breathes, the way the
                # animated marks of the menu bar apps do
                f = 0.5 + 0.5 * abs(math.sin(time.monotonic() * 2.6))
                color = (*color[:3], color[3] * (0.45 + 0.55 * f))
            else:
                f = 1.0
            text = str(st.get("text") or "")
            tw = draw.text_width(cr, text, font2) if text else 0.0
            size = glyph
            iw = size
            pixbuf = None
            icon = str(st.get("icon") or "")
            if icon:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon, size, -1)
                except Exception:  # noqa: BLE001
                    pixbuf = None
            if pixbuf is not None:
                w0, h0 = pixbuf.get_width(), pixbuf.get_height()
                if w0 <= 0 or h0 <= 0:
                    iw = 0.0
                else:
                    f = size / max(w0, h0)
                    cr.save()
                    cr.translate(right - w0 * f, (bar - h0 * f) / 2)
                    cr.scale(f, f)
                    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                    cr.paint_with_alpha(f)
                    cr.restore()
                    iw = w0 * f
            else:
                name = str(st.get("glyph") or st["id"])
                fn = getattr(glyphs, name, None)
                if fn is not None:
                    fn(cr, right - size, (bar - size) / 2, size, color)
                else:
                    # no glyph of that name: the first letter in a soft
                    # disc, the way a thumbnail app would badge it
                    r = size / 2
                    cx0 = right - size
                    cr.arc(cx0 + r, bar / 2, r - 1, 0, 2 * math.pi)
                    cr.set_source_rgba(*pal["text_faint"])
                    cr.fill()
                    draw.draw_text(cr, cx0 + r, bar / 2 + 1,
                                   name[:1].upper(), size * 0.75, color,
                                   align="center", baseline="middle")
            if text:
                draw.draw_text(cr, right - iw - 3 * s, bar / 2, text, font2,
                               color, align="right", baseline="middle")
            w = iw + (tw + 3 * s if text else 0.0)
            self._status_hits.append((right - w, w, st))
            right -= w + m.px("status_gap")

    # -- input ---------------------------------------------------------------

    def on_motion(self, x, y):
        # the menu bar covers the whole top of the screen, so it doubles as
        # the sensor that brings the notch back
        self.shell.pointer_moved("top", y)
        return False

    def on_click(self, x, y, button):
        m = self.metrics
        # the menu bar extras first: they live on the end the system
        # status icons leave to the left
        for slot_x, slot_w, item in getattr(self, "_tray_x", []):
            if slot_x <= x <= slot_x + slot_w:
                if button == 3:
                    self._open_tray_menu(item)
                else:
                    self.shell.tray_item(item)
                return True
        for slot_x, slot_w, st in getattr(self, "_status_hits", []):
            if slot_x <= x <= slot_x + slot_w:
                self._run_status_item(st)
                return True
        if hasattr(self, "_clock_x") and \
                self._clock_x <= x <= self._clock_x + self._clock_w:
            self.shell.toggle_notification_centre()
            return True
        if hasattr(self, "_battery_x") and \
                self._battery_x <= x <= self._battery_x + self._battery_w:
            self.shell.open_popup("battery", x)
            return True
        if hasattr(self, "_mic_x") and \
                self._mic_x <= x <= self._mic_x + m.px("status_glyph"):
            if button == 1:
                state.toggle_dictation()
                self.redraw()
            return True
        if hasattr(self, "_profile_x") and \
                self._profile_x <= x <= self._profile_x + m.px("status_glyph"):
            self.shell.open_profiles_menu(x)
            return True
        if hasattr(self, "_wifi_x") and \
                self._wifi_x <= x <= self._wifi_x + m.px("status_glyph"):
            self.shell.open_popup("wifi", x)
            return True
        if hasattr(self, "_cc_x") and self._cc_x <= x <= self._cc_x + m.px("status_glyph"):
            self.shell.toggle_control_center()
            return True
        if hasattr(self, "_spotlight_x") and \
                self._spotlight_x <= x <= self._spotlight_x + m.px("status_glyph"):
            self.shell.open_spotlight()
            return True
        for item in self._items:
            if item["x"] <= x <= item["x"] + item["w"]:
                name = item["name"]
                if name in ("__apple__", "__app__"):
                    self.shell.toggle_apple_menu(x)
                else:
                    for title, entries in menus.menus_for(self._app_id):
                        if title == name:
                            self.shell.open_menu(title, entries, x)
                            return True
        return False

    def on_scroll(self, x, y, direction):
        return False

    def _pulse_tick(self):
        """The breath of a working program's badge: ~15fps while alive."""
        items = getattr(self, "_status_items_cache", None) or []
        if not any(st.get("pulse") for st in items):
            self._pulse_id = None
            return False
        self.redraw()
        return True

    def _color_of(self, st, pal):
        """The tint of a status item: a palette key, an accent name or #hex."""
        c = str(st.get("color") or "text")
        if c.startswith("#") and len(c) == 7:
            try:
                return (int(c[1:3], 16) / 255, int(c[3:5], 16) / 255,
                        int(c[5:7], 16) / 255, 1.0)
            except ValueError:
                pass
        named = _metrics.ACCENTS.get(c)
        if named is not None:
            return (*named, 1.0)
        return pal.get(c, None) or pal["text"]

    def _run_status_item(self, st):
        """A click on a program's item: the menu when it has one, the
        command otherwise, the way statusItem.menu replaces button.action."""
        menu = st.get("menu")
        if menu:
            self._open_status_menu(st)
            return
        run = str(st.get("run") or "").strip()
        if not run:
            return
        env = dict(os.environ)
        env["MACSHELL_STATUS_ITEM"] = st["id"]
        try:
            subprocess.Popen(run, shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env=env)
        except Exception:  # noqa: BLE001
            pass

    def _open_status_menu(self, st):
        """The pull-down of a program's badge, the way macOS shows it."""
        shell = self.shell
        rows = []
        for entry in st.get("menu", []):
            label = str(entry.get("label") or "")
            if label == "---":
                continue
            rows.append({
                "glyph": "claude" if st["id"] == "claude" else "grid",
                "label": label,
                "detail": "",
                "active": bool(entry.get("run")),
                "action": (lambda cmd=entry.get("run"), ref=st["id"]:
                           subprocess.Popen(
                               cmd, shell=True, start_new_session=True,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               env={**os.environ,
                                    "MACSHELL_STATUS_ITEM": ref})
                           if cmd else None),
            })
        if not rows:
            return
        menu = shell.popups.get("tray") or shell.popups["wifi"]
        hit = next((r for r in getattr(self, "_status_hits", [])
                    if r[2]["id"] == st["id"]), None)
        menu.show_items(st.get("title") or st["id"], rows,
                        anchor_x=(hit[0] + hit[1] / 2) if hit else None)

    def open_menu_by_title(self, title):
        """Open one of the application menus by name."""
        for item in self._items:
            if item["name"] == title:
                for name, entries in menus.menus_for(self._app_id):
                    if name == title:
                        self.shell.open_menu(title, entries, item["x"])
                        return True
        return False

    def _open_tray_menu(self, item):
        """The menu of a menu bar extra: what its program hands over."""
        shell = self.shell
        rows = []
        for row in item.menu_rows():
            if row["label"] == "---":
                continue
            rows.append({
                "glyph": "grid",
                "label": row["label"],
                "detail": "",
                "active": False,
                "action": (lambda row_id=row["id"], it=item:
                           it.click_menu_item(row_id)),
            })
        if rows:
            menu = shell.popups.get("tray") or shell.popups["wifi"]
            menu.show_items(item.title or item.id or "Menu", rows)
        else:
            item.context_menu(shell.tray._connection)
