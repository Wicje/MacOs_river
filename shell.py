#!/usr/bin/env python3
"""macOS Tahoe shell for Wayland.

One Python process hosts every panel: menu bar, dock, control centre,
widget column and the dropdown menus.  Keeping them together costs a
single interpreter instead of one per widget, which matters on a 4 GB
machine.

The shell talks to the compositor only through the layer-shell protocol,
so it runs unchanged on River, Sway and SwayFX.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from .macui import actions, state  # noqa: E402
from .macui.metrics import Metrics  # noqa: E402
from .panels.about import About  # noqa: E402
from .panels.assistant import Assistant  # noqa: E402
from .panels.controlcenter import ControlCentre  # noqa: E402
from .panels.forcequit import ForceQuit  # noqa: E402
from .panels.launchpad import Launchpad  # noqa: E402
from .panels.missioncontrol import MissionControl  # noqa: E402
from .panels.notificationcenter import NotificationCentre  # noqa: E402
from .panels.spaces import Spaces  # noqa: E402
from .panels.popup import StatusPopup  # noqa: E402
from .macui.tray import Tray  # noqa: E402
from .panels.settings import Settings  # noqa: E402
from .panels.dock import Dock  # noqa: E402
from .panels.dropdown import Dropdown  # noqa: E402
from .panels.menubar import MenuBar  # noqa: E402
from .panels.notch import Notch  # noqa: E402
from .panels.desktopicons import DesktopIcons  # noqa: E402
from .panels.desktopmenu import DesktopMenu  # noqa: E402
from .panels.sensor import Sensor  # noqa: E402
from .panels.snapzone import SnapZone  # noqa: E402
from .panels.quicklook import QuickLook  # noqa: E402
from .panels.screenshothud import ScreenshotHUD  # noqa: E402
from .panels.stagemanager import StageManager  # noqa: E402
from .panels.switcher import Switcher  # noqa: E402
from .panels.spotlight import Spotlight  # noqa: E402
from .panels.widgets import Widgets  # noqa: E402

APPLE_MENU = [
    {"label": "About This Mac", "action": "about"},
    {"separator": True},
    {"label": "System Settings…", "action": "control_centre"},
    {"label": "App Store…", "action": actions.open_store},
    {"separator": True},
    {"label": "Recent Items", "enabled": False},
    {"separator": True},
    {"label": "Hide Dock", "action": "toggle_dock",
     "label_fn": lambda: ("Show Dock"
                          if not self.metrics.config.get("show_dock", True)
                          else "Hide Dock")},
    {"label": "Hide Notch", "action": "toggle_notch",
     "label_fn": lambda: ("Show Notch"
                          if not self.metrics.config.get("show_notch", True)
                          else "Hide Notch")},
    {"separator": True},
    {"label": "Force Quit…", "action": "force_quit"},
    {"separator": True},
    {"label": "Sleep", "action": actions.suspend},
    {"label": "Restart…", "action": actions.reboot},
    {"label": "Shut Down…", "action": actions.poweroff},
    {"separator": True},
    {"label": "Log Out", "action": actions.log_out},
]

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
CMD_FIFO = os.path.join(RUNTIME, "macshell.cmd")


class Shell:
    def __init__(self):
        self.metrics = Metrics()
        state.start_refresher()
        # the start of the machine plays its chime, once the panels are up
        from .macui import sound  # noqa: E402
        GLib.timeout_add_seconds(2, lambda: (sound.startup(), False)[1])
        self.dropdown = Dropdown(self.metrics, self)
        self.menubar = MenuBar(self.metrics, self)
        self.tray = Tray()
        self.tray.on_change(lambda: GLib.idle_add(self.menubar.redraw))
        self.notch = Notch(self.metrics, self)
        self.dock = Dock(self.metrics, self)
        self.control_centre = ControlCentre(self.metrics, self)
        self.widgets = Widgets(self.metrics, self)
        self.desktop_icons = DesktopIcons(self.metrics, self)
        # the receiver of the clicks of the empty desktop: mapped first,
        # so it lies under the icons and the widget column
        self.desktop_menu = DesktopMenu(self.metrics, self)
        self.switcher = Switcher(self.metrics, self)
        self.quicklook = QuickLook(self.metrics, self)
        self.stage_manager = StageManager(self.metrics, self)
        self.screenshot_hud = ScreenshotHUD(self.metrics, self)
        self.assistant = Assistant(self.metrics, self)
        # the edges of the screen are the hot zones of the dock and the
        # notch; the strips are mapped after the panels, so they always
        # get the pointer
        self.sensors = [Sensor(self.metrics, self, "top"),
                        Sensor(self.metrics, self, "bottom")]
        self.snap_zone = SnapZone(self.metrics, self)
        self._notch_until = 0.0
        self._dock_until = 0.0
        self._at_edge = None
        self._over_dock = False
        self._dock_shown = None
        self._notch_shown = None
        self._focus_key = None
        self._focus_tag = 1
        self.spotlight = Spotlight(self.metrics, self)
        self.launchpad = Launchpad(self.metrics, self)
        self.mission_control = MissionControl(self.metrics, self)
        self.notification_centre = NotificationCentre(self.metrics, self)
        self.spaces = Spaces(self.metrics, self)
        self.settings = Settings(self.metrics, self)
        self.popups = {}
        for kind in ("wifi", "bluetooth", "battery", "volume"):
            self.popups[kind] = StatusPopup(self.metrics, self, kind)
        self._tag = 1
        self._last_command = ""
        self._last_command_time = 0.0
        self.about = About(self.metrics, self)
        self.force_quit = ForceQuit(self.metrics, self)
        self.windows = [
            self.menubar, self.notch, self.dock, self.desktop_menu,
            self.widgets,
            self.desktop_icons, self.switcher, self.quicklook,
            self.stage_manager, self.screenshot_hud, self.assistant,
            self.control_centre, self.dropdown, self.spotlight,
            self.launchpad, self.mission_control, self.notification_centre,
            self.spaces, self.settings, self.about, self.force_quit,
        ] + list(self.popups.values()) + [self.snap_zone] + self.sensors

    # -- lifecycle -----------------------------------------------------------

    def run(self):
        for window in self.windows:
            window.show_all()
        # the flyouts stay hidden until they are asked for
        self.dropdown.hide()
        self.control_centre.hide()
        self.spotlight.hide()
        self.launchpad.hide()
        self.mission_control.hide()
        self.notification_centre.hide()
        self.settings.hide()
        self.switcher.hide()
        self.quicklook.hide()
        self.stage_manager.hide()
        self.screenshot_hud.hide()
        self.assistant.hide()
        self.snap_zone.hide()
        for popup in self.popups.values():
            popup.hide()
        self.about.hide()
        self.force_quit.hide()
        self.widgets.set_visible(self.metrics.config.get("show_widgets", True))
        self.desktop_icons.set_visible(
            self.metrics.config.get("show_desktop_icons", True))
        # the dock and the notch decide for themselves whether they belong
        # on the screen: the desktop shows the dock, an application hides it
        self._sync_panels()

        # MACSHELL_SHOW_CC=1 opens the control centre straight away, which
        # makes it possible to check its layout without a mouse
        if os.environ.get("MACSHELL_SHOW_CC"):
            self.control_centre.show_all()
        if os.environ.get("MACSHELL_SHOW_SPOTLIGHT"):
            self.spotlight.open()

        GLib.timeout_add(1000, self._tick)
        GLib.timeout_add(120, self._tick_panels)
        GLib.timeout_add(2000, self._refresh_state)
        self._listen_for_commands()
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
        Gtk.main()

    # -- command channel -----------------------------------------------------
    #
    # The compositor cannot send key presses to a layer-shell surface that
    # does not have keyboard focus, so keyboard shortcuts are delivered
    # through a small fifo instead:  echo cc > $XDG_RUNTIME_DIR/macshell.cmd

    def _listen_for_commands(self):
        try:
            os.mkfifo(CMD_FIFO, 0o600)
        except FileExistsError:
            pass
        except OSError as exc:
            print(f"macshell: cannot create the command fifo: {exc}",
                  file=sys.stderr, flush=True)
            return
        try:
            fd = os.open(CMD_FIFO, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            print(f"macshell: cannot open the command fifo: {exc}",
                  file=sys.stderr, flush=True)
            return
        GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, fd, GLib.IO_IN,
                               self._on_command, None)

    def _on_command(self, fd, _condition, _user_data=None):
        try:
            data = os.read(fd, 4096).decode("utf-8", "replace")
        except OSError:
            return True
        for command in data.split("\n"):
            command = command.strip()
            if command:
                self.run_command(command)
        return True

    def run_command(self, command):
        """Handle one command from the fifo.

        Key repeats would otherwise toggle a panel dozens of times per
        second, so the same command is ignored for a moment.
        """
        now = time.monotonic()
        if command == self._last_command and now - self._last_command_time < 0.6:
            return
        self._last_command = command
        self._last_command_time = now
        if command == "cc":
            self.toggle_control_center()
        elif command == "spotlight":
            self.open_spotlight()
        elif command == "apple":
            self.toggle_apple_menu(20)
        elif command.startswith("menu:"):
            title = command.split(":", 1)[1]
            self.menubar.open_menu_by_title(title)
        elif command == "theme":
            actions.toggle_theme()
        elif command == "dock":
            self.hide_dock()
        elif command == "dock:show":
            self.show_dock()
        elif command == "notch":
            self.hide_notch()
        elif command == "notch:show":
            self.show_notch()
        elif command == "launchpad":
            self.launchpad.toggle()
        elif command == "widgets":
            self.toggle_widgets()
        elif command == "switcher":
            self.switcher.toggle()
        elif command == "stage":
            self.stage_manager.toggle()
        elif command.startswith("tile:"):
            zone = command.split(":", 1)[1]
            self.snap_window(zone)
        elif command == "ask":
            self.assistant.open("ask")
        elif command == "write":
            self.assistant.open("write")
        elif command == "screen":
            self.assistant.open("screen")
        elif command == "screenshot:hud":
            self.screenshot_hud.toggle()
        elif command.startswith("quicklook:"):
            self.quicklook.show_file(command.split(":", 1)[1], "look")
        elif command.startswith("getinfo:"):
            self.quicklook.show_file(command.split(":", 1)[1], "info")
        elif command == "desktopicons":
            self.toggle_desktop_icons()
        elif command == "windows":
            self.mission_control.toggle()
        elif command == "notifications":
            self.notification_centre.toggle()
        elif command == "settings":
            self.open_settings()
        elif command.startswith("tag "):
            try:
                self.switch_tag(int(command.split(" ", 1)[1]))
            except ValueError:
                pass
        elif command.startswith("settings:"):
            self.settings.section = command.split(":", 1)[1]
            self.open_settings()
        elif command == "clipboard":
            self.open_clipboard()
        elif command == "focus":
            self.open_focus_menu()
        elif command == "screenshot":
            subprocess.Popen([f"{os.path.expanduser('~/.config/river/screenshot.sh')}",
                              "region"], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif command == "dockmenu":
            from .panels import dock as dock_module
            if dock_module.APPS:
                self.open_dock_menu(dock_module.APPS[1], 1)
        elif command.startswith("dockclick:"):
            try:
                index = int(command.split(":", 1)[1])
            except ValueError:
                index = -1
            self.dock.activate_index(index)
        elif command.startswith("popup:"):
            self.open_popup(command.split(":", 1)[1])
        elif command == "close":
            actions.close_window()
        elif command == "lock":
            actions.lock_session()
        elif command == "debug":
            self._debug()

    def _debug(self):
        """Write the state of the panels to the journal."""
        entries = state.toplevels()
        activated = [entry.get("title") for entry in entries
                     if entry.get("activated")]
        print(f"macshell: tag={self._tag} focus_key={self._focus_key} "
              f"focus_tag={self._focus_tag} activated={activated} "
              f"in_front={self._app_in_front()} "
              f"dock_mode={self.metrics.config.get('dock_mode')} "
              f"dock_shown={self._dock_shown} visible={self.dock.get_visible()} "
              f"slide={self.dock._slide_value} "
              f"alloc={self.dock.area.get_allocation().width}x"
              f"{self.dock.area.get_allocation().height} "
              f"edge={self._at_edge} over={self._over_dock} "
              f"layout={[(i['index'], round(i['x']), round(i['size'])) for i in self.dock._layout]} "
              f"region={self.dock.input_rects()} "
              f"click={self.dock._last_click}",
              file=sys.stderr, flush=True)

    def _tick(self):
        if self.metrics.reload():
            self._repaint()
        self.menubar.refresh()
        return True

    def _tick_panels(self):
        """The dock and the notch follow the pointer and the focus."""
        self._sync_panels()
        return True

    # -- the auto hiding dock and notch --------------------------------------
    #
    # macOS keeps the dock on the desktop, but it steps out of the way as
    # soon as an application takes the focus and comes back when the
    # pointer reaches the edge of the screen.  The same goes for the notch:
    # it is out of sight until the pointer reaches the top of the display.
    #
    # Three modes are possible for each of them:
    #
    #   always   the panel never hides
    #   desktop  the panel is visible while the desktop shows
    #   auto     the panel is only visible at the edge of the screen

    def pointer_moved(self, edge, absolute_y):
        """The pointer reached an edge of the screen."""
        screen_h = self.metrics.height or 768
        now = time.monotonic()
        if edge == "top":
            if absolute_y <= 6:
                self._notch_until = now + 2.5
            elif absolute_y > 60:
                self._notch_until = 0
        elif edge == "bottom":
            # the pointer is in the strip along the bottom edge: the dock
            # stays there until the pointer leaves again
            if absolute_y >= screen_h - 6:
                self._at_edge = "bottom"
            else:
                self._at_edge = None
        self._sync_panels()

    def pointer_left(self, edge):
        """The pointer left an edge of the screen."""
        if edge == "bottom" and self._at_edge == "bottom":
            self._at_edge = None
            self._sync_panels()


    def snap_window(self, zone):
        """Snap the focused window to the left or the right half.

        The rectangle of macOS is only drawn for the two halves; the
        quarters are tiled without it.
        """
        self.snap_zone.show_zone(zone if zone in ("left", "right") else "")
        actions.tile_window(zone)
        GLib.timeout_add(600, self.snap_zone.close)

    def keep_alive(self, which):
        """The pointer is over a panel, so it stays visible."""
        now = time.monotonic()
        if which == "dock":
            self._over_dock = True
            self._dock_until = now + 2.5
        else:
            self._notch_until = now + 2.5

    def panel_left(self, which):
        """The pointer left a panel."""
        if which == "dock":
            self._over_dock = False
            self._sync_panels()

    def _app_in_front(self):
        """True when an application window covers the screen.

        River keeps the activation of the last focused window, even when
        the window sits on another workspace, so the activation alone is
        not enough: the window is only in front when it was focused on the
        workspace that is on screen now.
        """
        key = None
        for entry in state.toplevels():
            if entry.get("activated"):
                key = (entry.get("app_id") or "", entry.get("title") or "")
                break
        if key is None:
            self._focus_key = None
            return False
        if key != self._focus_key:
            # another window took the focus: it belongs to this workspace
            self._focus_key = key
            self._focus_tag = self._tag
            return True
        return self._focus_tag == self._tag

    def _sync_panels(self):
        """Show or hide the dock and the notch the way macOS does."""
        cfg = self.metrics.config
        now = time.monotonic()

        # -- the dock ------------------------------------------------------
        show_dock = bool(cfg.get("show_dock", True))
        if show_dock:
            mode = cfg.get("dock_mode", "desktop")
            if mode == "always":
                pass
            elif self._over_dock or self._at_edge == "bottom":
                # the pointer is at the bottom of the screen or over the
                # dock: it stays there
                pass
            elif self._dock_until > now:
                # the dock was asked for a moment ago
                pass
            elif mode == "desktop" and not self._app_in_front():
                # the desktop shows: the dock belongs on the screen
                pass
            else:
                show_dock = False
        if show_dock != self._dock_shown:
            self._dock_shown = show_dock
            self.dock.set_shown(show_dock)

        # -- the notch -----------------------------------------------------
        show_notch = bool(cfg.get("show_notch", True))
        if show_notch:
            mode = cfg.get("notch_mode", "auto")
            if mode == "always":
                pass
            elif self._notch_until > now:
                pass
            elif getattr(self.notch, "_activities", None):
                # the island takes part: something is happening, and the
                # notch stays up to tell about it, the way macOS does
                pass
            else:
                show_notch = False
        if show_notch != self._notch_shown:
            self._notch_shown = show_notch
            self.notch.set_shown(show_notch)

    def _repaint(self):
        for window in self.windows:
            window.redraw()

    def _refresh_state(self):
        self.widgets.refresh()
        self.desktop_icons.refresh()
        self.notch.refresh()
        self.dock.refresh_running()
        self.spaces.refresh()
        if hasattr(self, "tray"):
            # the icons of the tray change with the state of their programs
            self.tray.refresh()
        return True

    # -- menu plumbing -------------------------------------------------------

    def open_menu(self, title, items, x):
        self.dropdown.open(title, items, x)

    def toggle_apple_menu(self, x):
        if self.dropdown.get_visible() and self.dropdown.title == "__apple__":
            self.dropdown.close()
        else:
            self.dropdown.open("__apple__", APPLE_MENU, x)

    def run_action(self, action):
        """Run a menu action, which may be a callable or a panel name."""
        if callable(action):
            action()
            return
        if action == "about":
            self.about.open()
        elif action == "control_centre":
            self.control_centre.show_all()
        elif action == "settings":
            self.open_settings()
        elif action == "force_quit":
            self.force_quit.open()
        elif action == "toggle_dock":
            self.toggle_dock()
        elif action == "toggle_notch":
            self.toggle_notch()
        elif action == "toggle_widgets":
            self.toggle_widgets()

    def close_menus(self):
        if self.dropdown.get_visible():
            self.dropdown.close()

    # -- panels --------------------------------------------------------------

    def toggle_control_center(self):
        self.control_centre.toggle_visible()

    def open_spotlight(self):
        self.spotlight.open()

    def open_launchpad(self):
        self.launchpad.toggle()

    def toggle_notification_centre(self):
        self.notification_centre.toggle()

    def open_settings(self):
        self.settings.open()

    def open_clipboard(self):
        """The clipboard history, the way the notch shows it."""
        rows = []
        text = ""
        try:
            out = subprocess.run(["cliphist", "list"], capture_output=True,
                                 text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        for line in out.splitlines()[:10]:
            if "\t" not in line:
                continue
            _index, _, text = line.partition("\t")
            text = text.strip()
            if not text:
                continue
            label = text if len(text) < 60 else text[:57] + "..."
            rows.append({
                "glyph": "clipboard",
                "label": label,
                "detail": "",
                "active": False,
                "action": (lambda text=text: subprocess.Popen(
                    ["wl-copy"], input=text.encode(),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)),
            })
        if not rows:
            rows.append({"glyph": "clipboard", "label": "The clipboard is empty",
                         "detail": "", "active": False, "action": None})
        else:
            # the writing tools, the way macOS offers them above the
            # clipboard history
            rows.insert(0, {
                "glyph": "sparkles",
                "label": "Writing Tools…",
                "detail": "",
                "active": False,
                "action": lambda: self.open_writing_tools(rows[1]["label"]
                                                         if len(rows) > 1 else ""),
            })
        menu = self.popups.get("clipboard")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items("Clipboard", rows, anchor_x=None)

    def open_quick_look(self, path, mode="look"):
        """Quick Look or Get Info for a file."""
        if not path or not os.path.exists(path):
            self.show_message("Quick Look", "That file is not there any more")
            return
        self.assistant.close()
        self.quicklook.show_file(path, mode)

    def open_file_menu(self, path):
        """The menu of a file, the way macOS shows it in the desktop."""
        name = os.path.basename(path)
        rows = [
            {"glyph": "grid", "label": "Open", "detail": "", "active": False,
             "action": lambda: state.spawn(f"xdg-open {path}")},
            {"glyph": "sparkles", "label": "Quick Look", "detail": "",
             "active": False, "action": lambda: self.open_quick_look(path)},
            {"glyph": "grid", "label": "Get Info", "detail": "", "active": False,
             "action": lambda: self.open_quick_look(path, "info")},
        ]
        menu = self.popups.get("file")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items(name, rows)

    def show_message(self, title, message):
        """A small message, the way macOS reports that something failed."""
        menu = self.popups.get("message")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items(title, [{
            "glyph": "grid",
            "label": message,
            "detail": "",
            "active": False,
            "action": None,
        }], anchor_x=None)

    def open_writing_tools(self, text=""):
        """The Writing Tools: rewrite, proofread, summarise a text."""
        if not text:
            try:
                text = subprocess.run(["wl-paste", "--no-newline"],
                                      capture_output=True, text=True,
                                      timeout=3).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                text = ""
        self.assistant.open("write", source=text)

    def open_focus_menu(self):
        """The focus modes, the way the Control Centre lists them."""
        modes = [
            ("Off", "off", False),
            ("Do Not Disturb", "do-not-disturb", False),
            ("Work", "work", False),
            ("Personal", "personal", False),
            ("Sleep", "sleep", False),
        ]
        current = state.dnd_mode()
        rows = []
        for label, mode, _ in modes:
            rows.append({
                "glyph": "moon" if mode != "off" else "check",
                "label": label,
                "detail": "on" if current == mode else "",
                "active": current == mode,
                "action": (lambda mode=mode: state.set_dnd_mode(mode)),
            })
        rows.append({
            "glyph": "moon", "label": "Night Shift", "detail": "",
            "active": False,
            "action": lambda: state.spawn(
                f"{os.path.expanduser('~/.config/river/nightlight.py')}"),
        })
        menu = self.popups.get("focus")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items("Focus", rows)

    def open_profiles_menu(self, anchor_x=None):
        """The power profiles, the way the battery zone lists them."""
        current = state.power_mode()
        labels = {
            "performance": "High Power",
            "balanced": "Balanced",
            "power-saver": "Low Power",
        }
        rows = []
        for mode, label in labels.items():
            rows.append({
                "glyph": "check" if current == mode else "",
                "label": label,
                "active": current == mode,
                "action": (lambda mode=mode: state.set_power_mode(mode)),
            })
        menu = self.popups.get("profiles")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items("Power Profile", rows)

    def open_popup(self, kind, anchor_x=None):
        for popup in self.popups.values():
            popup.close()
        self.popups[kind].toggle(anchor_x)

    def tray_item(self, item):
        """The click on a menu bar extra: the item decides what it does."""
        if hasattr(self, "tray"):
            item.activate(self.tray._connection)

    # -- the desktop itself --------------------------------------------------

    def desktop_clicked(self):
        """A click on the empty desk dismisses the open panels."""
        for panel in (self.dropdown, self.control_centre, self.spotlight,
                      self.notification_centre, self.launchpad,
                      self.mission_control, self.assistant):
            if panel.get_visible():
                panel.hide()
        self.close_menus()
        for popup in self.popups.values():
            popup.close()

    def open_desktop_menu(self):
        """The menu of the desktop of macOS: a new folder, the wall of
        the desk, the widgets."""
        rows = [
            {"glyph": "grid", "label": "New Folder", "detail": "",
             "active": False, "action": self.new_desktop_folder},
            {"glyph": "sparkles", "label": "Change Wallpaper…",
             "detail": "", "active": False,
             "action": lambda: state.spawn(
                 f"{os.path.expanduser('~/.config/river/wallpaper-pick.sh')}")},
            {"glyph": "grid",
             "label": ("Hide Widgets"
                       if self.metrics.config.get("show_widgets", True)
                       else "Show Widgets"),
             "detail": "", "active": False,
             "action": self.toggle_widgets},
            {"glyph": "grid", "label": "System Settings…", "detail": "",
             "active": False, "action": self.open_settings},
        ]
        menu = self.popups.get("desktop") or self.popups["wifi"]
        menu.show_items("Desktop", rows)

    def new_desktop_folder(self):
        """A folder on the desk, named the way Finder names them."""
        desktop = os.path.expanduser("~/Desktop")
        name = "untitled folder"
        path = os.path.join(desktop, name)
        count = 2
        while os.path.exists(path):
            path = os.path.join(desktop, f"untitled folder {count}")
            count += 1
        try:
            os.makedirs(path)
        except OSError:
            return
        self.desktop_icons.refresh()
        self.show_message("Desktop", f"“{os.path.basename(path)}” is new")

    # -- the dock's context menu --------------------------------------------

    def open_dock_menu(self, app, index):
        """The menu macOS shows when the dock icon is clicked with the right
        button."""
        from .panels import dock as dock_module

        if app.get("id") == "trash":
            rows = [
                {"glyph": "grid", "label": "Open", "detail": "",
                 "active": False,
                 "action": lambda: state.spawn("dolphin trash:///")},
                {"glyph": "close", "label": "Empty Trash", "detail": "",
                 "active": False, "action": self.empty_trash},
            ]
            menu = self.popups.get("dock") or self.popups["wifi"]
            menu.show_items("Trash", rows, anchor_x=None,
                            anchor_y=int(self.metrics.height * 0.72))
            return

        rows = []
        in_dock = any(item["id"] == app["id"] for item in dock_module.APPS)
        if in_dock and index > 0 and index < len(dock_module.APPS):
            rows.append({
                "glyph": "grid", "label": "Move Left", "detail": "",
                "active": False,
                "action": lambda: self.move_in_dock(index, -1),
            })
            rows.append({
                "glyph": "grid", "label": "Move Right", "detail": "",
                "active": False,
                "action": lambda: self.move_in_dock(index, 1),
            })
        if in_dock:
            rows.append({
                "glyph": "grid", "label": "Remove from Dock", "detail": "",
                "active": False,
                "action": lambda: self.remove_from_dock(app["id"]),
            })
        else:
            rows.append({
                "glyph": "grid", "label": "Keep in Dock", "detail": "",
                "active": False,
                "action": lambda: self.keep_in_dock(app),
            })
        rows.append({
            "glyph": "close", "label": "Quit", "detail": "", "active": False,
            "action": lambda: self.quit_app(app.get("app") or ""),
        })
        rows.append({
            "glyph": "chevron_down", "label": "Options…", "detail": "",
            "active": False, "action": self.open_settings,
        })

        menu = self.popups.get("dock")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items(app.get("label", "Application"), rows,
                        anchor_x=None,
                        anchor_y=int(self.metrics.height * 0.72))

    def remove_from_dock(self, app_id):
        from .panels import dock as dock_module

        dock_module.APPS = [app for app in dock_module.APPS
                            if app["id"] != app_id]
        dock_module._save_apps(dock_module.APPS)
        self.dock.reload_apps()

    def keep_app_in_dock(self, entry):
        """Add an application of the launchpad to the dock."""
        app = {
            "id": entry.get("id", ""),
            "label": entry.get("name", entry.get("id", "")),
            "cmd": entry.get("exec", ""),
            "app": entry.get("id", ""),
        }
        if not app["id"] or not app["cmd"]:
            return
        self.keep_in_dock(app)

    def open_app_menu(self, entry):
        """The menu of an application, the way macOS shows it."""
        from .panels import dock as dock_module

        in_dock = any(item["id"] == entry.get("id")
                      for item in dock_module.APPS)
        rows = []
        if not in_dock:
            rows.append({
                "glyph": "grid", "label": "Keep in Dock", "detail": "",
                "active": False,
                "action": lambda: self.keep_app_in_dock(entry),
            })
        rows.append({
            "glyph": "grid", "label": "Open", "detail": "", "active": False,
            "action": lambda: state.spawn(entry.get("exec", "")),
        })
        menu = self.popups.get("app")
        if menu is None:
            menu = self.popups["wifi"]
        menu.show_items(entry.get("name", "Application"), rows)

    def keep_in_dock(self, app):
        from .panels import dock as dock_module

        if any(item["id"] == app["id"] for item in dock_module.APPS):
            return
        dock_module.APPS.append(app)
        dock_module._save_apps(dock_module.APPS)
        self.dock.reload_apps()

    def move_in_dock(self, index, delta):
        """Move a dock icon one place to the left or the right."""
        from .panels import dock as dock_module

        other = index + delta
        if not (0 <= other < len(dock_module.APPS)):
            return
        # the index counts the recent programs as well; the pinned list
        # keeps its own order, so the recent programs cannot be moved
        items = self.dock._items()
        if index >= len(items) or not items[index].get("id"):
            return
        pinned_index = index
        for item in dock_module.APPS:
            if item["id"] == items[index]["id"]:
                break
            pinned_index -= 1
        other_index = pinned_index + delta
        if not (0 <= other_index < len(dock_module.APPS)):
            return
        position = dock_module.APPS.index(items[index])
        other_pos = dock_module.APPS.index(dock_module.APPS[other_index])
        dock_module.APPS[position], dock_module.APPS[other_pos] = (dock_module.
            APPS[other_pos], dock_module.APPS[position])
        dock_module._save_apps(dock_module.APPS)
        self.dock.reload_apps()

    def empty_trash(self):
        """The trash of the machine, the way macOS empties it."""
        import shutil
        trash = os.path.expanduser("~/.local/share/Trash")
        removed = 0
        for subdir in ("files", "info"):
            directory = os.path.join(trash, subdir)
            if not os.path.isdir(directory):
                continue
            for name in os.listdir(directory):
                path = os.path.join(directory, name)
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    removed += 1
                except OSError:
                    pass
        self.show_message("Trash",
                          f"{removed} items{" are" if removed != 1 else " is"} out")

    def quit_app(self, app_id):
        if not app_id:
            return
        for entry in state.window_list():
            if (entry[0] or "").lower() == app_id.lower():
                actions.activate_window(entry[1])
                actions.kill_window(entry[1])

    # -- syncing the config with the panels ---------------------------------

    def sync_dock(self):
        self._sync_panels()

    def sync_notch(self):
        self._sync_panels()

    def sync_widgets(self):
        self.widgets.set_visible(self.metrics.config.get("show_widgets", True))
        self.desktop_icons.set_visible(
            self.metrics.config.get("show_desktop_icons", True))

    def restart_wallpaper(self):
        subprocess.run(["systemctl", "--user", "restart",
                        "macshell-wallpaper.service"], capture_output=True)

    # -- helpers for the panels ---------------------------------------------

    def window_list(self):
        return state.window_list()

    def toplevel_state(self):
        return state.toplevels()

    def activate_app(self, app_id):
        """Bring an application to the front."""
        state.activate_app(app_id)

    def activate_window(self, title):
        actions.activate_window(title)

    def current_tag(self):
        return self._tag

    def switch_tag(self, tag):
        self._tag = tag
        actions.switch_tag(tag)
        # the dock owns a row per workspace: coding keeps its tools,
        # research the reader, and the media desk its players
        if hasattr(self, "dock"):
            self.dock.refresh_span(tag)
    # -- panel visibility ----------------------------------------------------

    def _set_config(self, key, value):
        self.metrics.config[key] = value
        self.metrics.save()

    def show_dock(self):
        self._set_config("show_dock", True)
        self._dock_until = time.monotonic() + 2.5
        self._sync_panels()

    def hide_dock(self):
        self._set_config("show_dock", False)
        self._dock_until = 0
        self._sync_panels()

    def toggle_dock(self):
        if self.metrics.config.get("show_dock", True):
            self.hide_dock()
        else:
            self.show_dock()

    def show_notch(self):
        self._set_config("show_notch", True)
        self._notch_until = time.monotonic() + 2.5
        self._sync_panels()

    def hide_notch(self):
        self._set_config("show_notch", False)
        self._notch_until = 0
        self._sync_panels()

    def toggle_notch(self):
        if self.metrics.config.get("show_notch", True):
            self.hide_notch()
        else:
            self.show_notch()

    def toggle_widgets(self):
        visible = not self.metrics.config.get("show_widgets", True)
        self._set_config("show_widgets", visible)
        self.widgets.set_visible(visible)

    def toggle_desktop_icons(self):
        visible = not self.metrics.config.get("show_desktop_icons", True)
        self._set_config("show_desktop_icons", visible)
        self.desktop_icons.set_visible(visible)


def main():
    Shell().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
