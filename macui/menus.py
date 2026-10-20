"""The menu bar's menus.

macOS shows a different set of menus for every application, and every item
does something real.  This module holds the definitions; the actions live
in :mod:`macshell.macui.actions`.
"""

from __future__ import annotations

from . import actions

SEPARATOR = {"separator": True}


def _item(label, action=None, shortcut=None, enabled=True):
    entry = {"label": label}
    if action is not None:
        entry["action"] = action
    if shortcut:
        entry["shortcut"] = shortcut
    if not enabled:
        entry["enabled"] = False
    return entry


# --- shared groups ----------------------------------------------------------

def edit_menu():
    return [
        _item("Undo", actions.undo, "⌘Z"),
        _item("Redo", actions.redo, "⇧⌘Z"),
        SEPARATOR,
        _item("Cut", actions.cut_selection, "⌘X"),
        _item("Copy", actions.copy_selection, "⌘C"),
        _item("Paste", actions.paste_selection, "⌘V"),
        SEPARATOR,
        _item("Select All", actions.select_all, "⌘A"),
    ]


def view_menu(zoom=True):
    items = []
    if zoom:
        items += [
            _item("Zoom In", lambda: actions.send("ctrl+plus"), "⌘+"),
            _item("Zoom Out", lambda: actions.send("ctrl+minus"), "⌘-"),
            _item("Actual Size", lambda: actions.send("ctrl+0"), "⌘0"),
            SEPARATOR,
        ]
    items.append(_item("Enter Full Screen", actions.toggle_fullscreen, "⌃⌘F"))
    return items


def window_menu(move_screen=True):
    items = [
        _item("Minimize", actions.minimize_window, "⌘M"),
        _item("Zoom", actions.zoom_window),
        SEPARATOR,
        _item("Tile Window to Left of Screen",
              lambda: actions.tile_window("left"), "⌃⌘←"),
        _item("Tile Window to Right of Screen",
              lambda: actions.tile_window("right"), "⌃⌘→"),
    ]
    if move_screen:
        items += [
            SEPARATOR,
            _item("Move Window to Left Screen",
                  lambda: actions.move_to_output("left")),
            _item("Move Window to Right Screen",
                  lambda: actions.move_to_output("right")),
        ]
    items += [
        SEPARATOR,
        _item("Bring All to Front", actions.bring_to_front, enabled=False),
    ]
    return items


def help_menu():
    return [
        _item("macOS Help", actions.open_help),
        _item("Keyboard Shortcuts", actions.open_shortcuts),
    ]


def file_menu(kind="app"):
    """The File menu of the generic application."""
    if kind == "browser":
        return [
            _item("New Window", lambda: actions.send("ctrl+n"), "⌘N"),
            _item("New Incognito Window", lambda: actions.send("ctrl+shift+n"),
                  "⇧⌘N"),
            _item("New Tab", lambda: actions.send("ctrl+t"), "⌘T"),
            SEPARATOR,
            _item("Open Location…", lambda: actions.send("ctrl+l"), "⌘L"),
            _item("Open File…", actions.choose_file),
            SEPARATOR,
            _item("Close Window", lambda: actions.send("ctrl+w"), "⌘W"),
            SEPARATOR,
            _item("Quit", lambda: actions.send("ctrl+q"), "⌘Q"),
        ]
    if kind == "files":
        return [
            _item("New Window", actions.new_files_window, "⌘N"),
            _item("Open…", actions.choose_file, "⌘O"),
            SEPARATOR,
            _item("Close Window", actions.close_window, "⌘W"),
            SEPARATOR,
            _item("Quit", actions.close_window, "⌘Q"),
        ]
    return [
        _item("New Window", actions.new_terminal, "⌘N"),
        _item("Open…", actions.choose_file, "⌘O"),
        SEPARATOR,
        _item("Close Window", actions.close_window, "⌘W"),
        SEPARATOR,
        _item("Quit", actions.close_window, "⌘Q"),
    ]


# --- per application menus --------------------------------------------------

def finder_menus():
    return [
        ("File", file_menu("app")),
        ("Edit", edit_menu()),
        ("View", view_menu()),
        ("Go", [
            _item("Back", lambda: actions.send("alt+Left"), "⌘["),
            _item("Forward", lambda: actions.send("alt+Right"), "⌘]"),
            SEPARATOR,
            _item("Go to Folder…", actions.choose_folder, "⇧⌘G"),
            _item("Go to Home", actions.open_home, "⇧⌘H"),
            _item("Go to Computer", actions.open_computer, "⇧⌘C"),
        ]),
        ("Window", window_menu()),
        ("Help", help_menu()),
    ]


def files_menus():
    return [
        ("File", file_menu("files")),
        ("Edit", edit_menu()),
        ("View", view_menu()),
        ("Go", [
            _item("Back", lambda: actions.send("alt+Left"), "⌘["),
            _item("Forward", lambda: actions.send("alt+Right"), "⌘]"),
            SEPARATOR,
            _item("Go to Folder…", actions.choose_folder, "⇧⌘G"),
            _item("Go to Home", actions.open_home, "⇧⌘H"),
            _item("Go to Computer", actions.open_computer, "⇧⌘C"),
        ]),
        ("Window", window_menu()),
        ("Help", help_menu()),
    ]


def terminal_menus():
    return [
        ("Shell", [
            _item("New Window", lambda: actions.send("ctrl+shift+n"), "⇧⌘N"),
            _item("New Tab", lambda: actions.send("ctrl+shift+t"), "⇧⌘T"),
            SEPARATOR,
            _item("Close Window", actions.close_window, "⇧⌘W"),
            SEPARATOR,
            _item("Quit", actions.close_window, "⌘Q"),
        ]),
        ("Edit", edit_menu()),
        ("View", view_menu() + [
            SEPARATOR,
            _item("Clear Scrollback", lambda: actions.send("ctrl+shift+k")),
        ]),
        ("Window", window_menu()),
        ("Help", help_menu()),
    ]


def browser_menus():
    return [
        ("File", file_menu("browser")),
        ("Edit", edit_menu() + [
            SEPARATOR,
            _item("Find…", lambda: actions.send("ctrl+f"), "⌘F"),
        ]),
        ("View", view_menu() + [
            SEPARATOR,
            _item("Reload", lambda: actions.send("ctrl+r"), "⌘R"),
            _item("Toggle Developer Tools",
                  lambda: actions.send("ctrl+shift+i")),
        ]),
        ("History", [
            _item("Back", lambda: actions.send("alt+Left"), "⌘["),
            _item("Forward", lambda: actions.send("alt+Right"), "⌘]"),
            SEPARATOR,
            _item("Show All History", lambda: actions.send("ctrl+h"), "⌘Y"),
        ]),
        ("Bookmarks", [
            _item("Bookmark This Tab", lambda: actions.send("ctrl+d"), "⌘D"),
            _item("Show Bookmarks", lambda: actions.send("ctrl+shift+o"),
                  "⇧⌘B"),
        ]),
        ("Window", window_menu(move_screen=False)),
        ("Help", help_menu()),
    ]


def media_menus():
    return [
        ("File", file_menu("app")),
        ("Edit", edit_menu()),
        ("Playback", [
            _item("Play / Pause", lambda: actions.send("space")),
            _item("Next Track", lambda: actions.send("ctrl+Right")),
            _item("Previous Track", lambda: actions.send("ctrl+Left")),
        ]),
        ("View", view_menu()),
        ("Window", window_menu()),
        ("Help", help_menu()),
    ]


FAMILIES = {
    "foot": terminal_menus,
    "footclient": terminal_menus,
    "alacritty": terminal_menus,
    "kitty": terminal_menus,
    "konsole": terminal_menus,
    "gnome-terminal": terminal_menus,
    "dolphin": files_menus,
    "org.kde.dolphin": files_menus,
    "nautilus": files_menus,
    "thunar": files_menus,
    "chromium": browser_menus,
    "chromium-browser": browser_menus,
    "google-chrome": browser_menus,
    "firefox": browser_menus,
    "firefox-esr": browser_menus,
    "org.mozilla.firefox": browser_menus,
    "mpv": media_menus,
    "vlc": media_menus,
    "audacity": media_menus,
    "obs": media_menus,
    "spotify": media_menus,
}


def menus_for(app_id):
    """The menus of the focused application."""
    family = FAMILIES.get((app_id or "").lower())
    if family is None:
        return finder_menus()
    return family()
