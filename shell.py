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
import sys
import time

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from .macui import actions, state  # noqa: E402
from .macui.metrics import Metrics  # noqa: E402
from .panels.about import About  # noqa: E402
from .panels.controlcenter import ControlCentre  # noqa: E402
from .panels.forcequit import ForceQuit  # noqa: E402
from .panels.launchpad import Launchpad  # noqa: E402
from .panels.missioncontrol import MissionControl  # noqa: E402
from .panels.notificationcenter import NotificationCentre  # noqa: E402
from .panels.spaces import Spaces  # noqa: E402
from .panels.dock import Dock  # noqa: E402
from .panels.dropdown import Dropdown  # noqa: E402
from .panels.menubar import MenuBar  # noqa: E402
from .panels.notch import Notch  # noqa: E402
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
        self.dropdown = Dropdown(self.metrics, self)
        self.menubar = MenuBar(self.metrics, self)
        self.notch = Notch(self.metrics, self)
        self.dock = Dock(self.metrics, self)
        self.control_centre = ControlCentre(self.metrics, self)
        self.widgets = Widgets(self.metrics, self)
        self.spotlight = Spotlight(self.metrics, self)
        self.launchpad = Launchpad(self.metrics, self)
        self.mission_control = MissionControl(self.metrics, self)
        self.notification_centre = NotificationCentre(self.metrics, self)
        self.spaces = Spaces(self.metrics, self)
        self._tag = 1
        self._last_command = ""
        self._last_command_time = 0.0
        self.about = About(self.metrics, self)
        self.force_quit = ForceQuit(self.metrics, self)
        self.windows = [
            self.menubar, self.notch, self.dock, self.widgets,
            self.control_centre, self.dropdown, self.spotlight,
            self.launchpad, self.mission_control, self.notification_centre,
            self.spaces, self.about, self.force_quit,
        ]

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
        self.about.hide()
        self.force_quit.hide()
        self.widgets.set_visible(self.metrics.config.get("show_widgets", True))
        self.dock.set_visible(self.metrics.config.get("show_dock", True))
        self.notch.set_visible(self.metrics.config.get("show_notch", True))

        # MACSHELL_SHOW_CC=1 opens the control centre straight away, which
        # makes it possible to check its layout without a mouse
        if os.environ.get("MACSHELL_SHOW_CC"):
            self.control_centre.show_all()
        if os.environ.get("MACSHELL_SHOW_SPOTLIGHT"):
            self.spotlight.open()

        GLib.timeout_add(1000, self._tick)
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
        except OSError:
            return
        try:
            fd = os.open(CMD_FIFO, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
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
        elif command == "windows":
            self.mission_control.toggle()
        elif command == "notifications":
            self.notification_centre.toggle()
        elif command == "close":
            actions.close_window()
        elif command == "lock":
            actions.lock_session()

    def _tick(self):
        if self.metrics.reload():
            self._repaint()
        self.menubar.refresh()
        return True

    def _repaint(self):
        for window in self.windows:
            window.redraw()

    def _refresh_state(self):
        self.widgets.refresh()
        self.notch.refresh()
        self.dock.refresh_running()
        self.spaces.refresh()
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

    # -- helpers for the panels ---------------------------------------------

    def window_list(self):
        return state.window_list()

    def activate_window(self, title):
        actions.activate_window(title)

    def current_tag(self):
        return self._tag

    def switch_tag(self, tag):
        self._tag = tag
        actions.switch_tag(tag)

    # -- panel visibility ----------------------------------------------------

    def _set_config(self, key, value):
        self.metrics.config[key] = value
        self.metrics.save()

    def show_dock(self):
        self._set_config("show_dock", True)
        self.dock.set_visible(True)

    def hide_dock(self):
        self._set_config("show_dock", False)
        self.dock.set_visible(False)

    def toggle_dock(self):
        if self.metrics.config.get("show_dock", True):
            self.hide_dock()
        else:
            self.show_dock()

    def show_notch(self):
        self._set_config("show_notch", True)
        self.notch.set_visible(True)

    def hide_notch(self):
        self._set_config("show_notch", False)
        self.notch.set_visible(False)

    def toggle_notch(self):
        if self.metrics.config.get("show_notch", True):
            self.hide_notch()
        else:
            self.show_notch()

    def toggle_widgets(self):
        visible = not self.metrics.config.get("show_widgets", True)
        self._set_config("show_widgets", visible)
        self.widgets.set_visible(visible)


def main():
    Shell().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
