"""The installed applications.

The desktop entries are parsed once and cached; the icons are looked up in
the usual icon directories.

The flatpak applications are entries of their own: flatpak exports them
into its own directories, and they are found there.
"""

from __future__ import annotations

import os
import re
import time

DESKTOP_DIRS = (
    "~/.local/share/applications",
    "/usr/share/applications",
    "/usr/local/share/applications",
    # the flatpak applications are exported into directories of their own
    "~/.local/share/flatpak/exports/share/applications",
    "/var/lib/flatpak/exports/share/applications",
)

ICON_SIZES = ("256x256", "128x128", "96x96", "64x64", "48x48", "32x32",
              "16x16")

# The icons the shell ships, and the programs they belong to.  A program
# is called differently by the compositor, by the desktop files and by
# the dock, and every one of those names is listed here, so a program
# looks the same in the dock and in the launchpad.
BUNDLED_ICONS = {
    "audacity": ("audacity",),
    "chromium": ("chromium", "chromium-browser", "google-chrome"),
    "dolphin": ("dolphin", "org.kde.dolphin"),
    "firefox": ("firefox", "firefox-esr", "org.mozilla.firefox"),
    "gimp": ("gimp", "org.gimp.GIMP"),
    "mpv": ("mpv",),
    "obs": ("obs", "com.obsproject.Studio"),
    "spotify": ("spotify", "com.spotify.Client", "spotify-player"),
    "steam": ("steam", "steamwebhelper"),
    "terminal": ("terminal", "foot", "footclient", "alacritty"),
    "trash": ("trash",),
    "vlc": ("vlc", "org.videolan.VLC"),
    "vscode": ("vscode", "code", "code-oss", "codium", "vscodium"),
}
ICON_DIRS = (
    "~/.local/share/icons",
    "/usr/share/icons",
    "/usr/share/pixmaps",
    "~/.local/share/flatpak/exports/share/icons",
    "/var/lib/flatpak/exports/share/icons",
)

# the icons of macOS: the theme the shell dresses itself with comes
# first, so a program gets its one icon and not the letter of a tile
THEME_DIRS = ("~/.local/share/icons/WhiteSur",)
THEME_SIZES = ("scalable", "128", "22", "16")

# how long the entries are kept before they are read again, so a program
# that is installed while the shell is running still shows up
CACHE_TTL = 30.0

_cache = None
_cache_all = None
_cache_time = 0.0

# Desktop entries in these categories are settings tools and helpers;
# macOS keeps them out of the application grid.
EXCLUDED_CATEGORIES = ("System", "Settings", "HardwareSettings",
                       "PackageManager", "Debugger")

# Helper programs that are installed as desktop entries but are not
# applications anybody would put in an application grid.
BLOCKED_IDS = {
    "bssh", "bvnc", "cmake-gui", "emacsclient", "opensuperclone",
    "opensupertool", "oscviewer", "org.rncbc.qpwgraph", "qv4l2", "qvidcap",
    "vgimp", "xgps", "xgpsspeed", "vim", "avahi-browse",
}


def _base_name(name):
    """Strip the version suffixes desktop files like to carry."""
    return re.sub(r"\s*\([\d.]+\)\s*(\(\d+\))?\s*$", "", name).strip()


def _clean_exec(command):
    """Strip the field codes desktop files use.

    The flatpak exports carry the file forwarding markers as well; they
    only mean something to flatpak itself, and a marker on its own would
    be taken for a file that does not exist.
    """
    command = re.sub(r"%[fFuUdDnNickvm]", "", command)
    command = command.replace("\\\\", "\\")
    words = [word for word in command.split() if word != "@@"]
    return " ".join(words)


def icon_path(name):
    """Find the icon file for a desktop entry."""
    if not name:
        return None
    if os.path.isabs(name) and os.path.exists(name):
        return name
    # the theme of macOS first: the icons keep their one look, and
    # programs that would fall back on the icons of the machine or on
    # the first letter of their name get dressed like macOS dresses them
    for root in THEME_DIRS:
        root = os.path.expanduser(root)
        for scope in ("apps", "places", "categories", "devices", "status"):
            for size in THEME_SIZES:
                for suffix in (".svg", ".png"):
                    candidate = os.path.join(
                        root, scope, size, name + suffix)
                    if os.path.exists(candidate):
                        return candidate
    for root in ICON_DIRS:
        root = os.path.expanduser(root)
        if root.endswith("pixmaps"):
            for suffix in (".png", ".svg", ".xpm"):
                candidate = os.path.join(root, name + suffix)
                if os.path.exists(candidate):
                    return candidate
            continue
        for size in ICON_SIZES:
            candidate = os.path.join(root, "hicolor", size, "apps", name + ".png")
            if os.path.exists(candidate):
                return candidate
        candidate = os.path.join(root, "hicolor", "scalable", "apps", name + ".svg")
        if os.path.exists(candidate):
            return candidate
    return None


def plain_key(value):
    """A name without the dots and the underscores.

    The compositor and the desktop files do not always spell a program
    the same way: the terminal is "footclient" in one and "foot" in the
    other, and LocalSend is "local_send" in one and "localsend" in the
    other.
    """
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _matches(entry, key):
    """True when a desktop entry is the application with that id."""
    if not key:
        return False
    if key in ((entry.get("id") or "").lower(),
               (entry.get("name") or "").lower()):
        return True
    plain = plain_key(key)
    if not plain:
        return False
    return plain in (plain_key(entry.get("id") or ""),
                     plain_key(entry.get("name") or ""))


def icon_for_app(name):
    """The icon of a desktop entry, by its name or by its id.

    The icon of a program is often a path of its own (an AppImage draws
    its icon from the file), so the desktop entry is asked first and the
    icon theme second.  When the entry does not carry an icon of its own,
    the name of the application is looked up in the theme as well: the
    compositor and the desktop files do not always agree on the name.
    """
    if not name:
        return None
    key = name.lower()
    for entry in all_applications():
        if _matches(entry, key):
            icon = entry.get("icon") or ""
            if os.path.isabs(icon) and os.path.exists(icon):
                return icon
            found = icon_path(icon)
            if found:
                return found
            break
    return icon_path(name)


def _read_entries(block=True):
    """Parse every desktop entry."""
    entries = {}
    for directory in DESKTOP_DIRS:
        directory = os.path.expanduser(directory)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".desktop"):
                continue
            path = os.path.join(directory, filename)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            if "NoDisplay=true" in text or "Hidden=true" in text:
                continue
            label = ""
            command = ""
            icon = ""
            categories = ""
            flatpak = False
            for line in text.splitlines():
                if line.startswith("Name=") and not label:
                    label = line[5:].strip()
                elif line.startswith("GenericName=") and not label:
                    label = line[11:].strip()
                elif line.startswith("Exec=") and not command:
                    command = line[5:].strip()
                elif line.startswith("Icon=") and not icon:
                    icon = line[5:].strip()
                elif line.startswith("Categories=") and not categories:
                    categories = line[10:].strip()
                elif line.startswith("X-Flatpak="):
                    flatpak = True
            if not label or not command:
                continue
            entry_id = filename[:-len(".desktop")]
            if block:
                if entry_id in BLOCKED_IDS:
                    continue
                if any(tag in categories for tag in EXCLUDED_CATEGORIES):
                    continue
            label = re.sub(r"\s*\([\d.]+\)\s*(\(\d+\))?\s*$", "", label)
            key = _base_name(label).lower()
            if key in entries:
                continue
            entries[key] = {
                "id": entry_id,
                "name": label,
                "exec": _clean_exec(command),
                "icon": icon,
                "flatpak": flatpak,
            }
    for app in entries.values():
        if app["id"] == "gimp":
            app["name"] = "GIMP"
        elif app["id"] == "mpv":
            app["name"] = "mpv"
    return sorted(entries.values(), key=lambda item: item["name"].lower())


def refresh():
    """Read the entries again, so a new program shows up."""
    global _cache, _cache_all, _cache_time
    _cache = None
    _cache_all = None
    _cache_time = 0.0


def applications():
    """The applications that belong in the application grid."""
    global _cache, _cache_time
    now = time.monotonic()
    if _cache is None or now - _cache_time > CACHE_TTL:
        _cache = _read_entries(block=True)
        _cache_time = now
    return list(_cache)


def all_applications():
    """Every entry, including the settings tools and helpers."""
    global _cache_all, _cache_time
    now = time.monotonic()
    if _cache_all is None or now - _cache_time > CACHE_TTL:
        _cache_all = _read_entries(block=False)
        _cache_time = now
    return list(_cache_all)


def bundled_icon_for(*names):
    """The name of the icon the shell ships for a program.

    The programs are looked up by their own name first and by the names
    they are known under afterwards, so a program that is called
    "org.kde.dolphin" by the compositor still finds the icon of the
    dock.
    """
    keys = [name.lower() for name in names if name]
    for key in keys:
        if key in BUNDLED_ICONS:
            return key
    for key in keys:
        for icon, aliases in BUNDLED_ICONS.items():
            if key in aliases:
                return icon
    return ""


def name_for_id(app_id):
    """The name of the application with that id.

    The id of a flatpak application is a mouthful, and the name of its
    desktop entry is what the user knows it by.
    """
    app_id = (app_id or "").lower()
    if not app_id:
        return ""
    for entry in all_applications():
        if _matches(entry, app_id):
            return entry.get("name") or ""
    return ""


def command_for_id(app_id):
    """The program of the application with that id.

    The compositor calls a program by the name of its desktop entry
    (org.kde.dolphin), while the dock calls it by the name of the
    program itself (dolphin); the two are tied together by the command
    the entry runs.
    """
    app_id = (app_id or "").lower()
    if not app_id:
        return ""
    for entry in all_applications():
        if _matches(entry, app_id):
            command = (entry.get("exec") or "").split()
            if not command:
                return ""
            name = os.path.basename(command[0])
            if name == "flatpak":
                # a flatpak program is run by flatpak, and the name of the
                # program is the id of its entry
                return entry.get("id") or ""
            return name
    return ""


def icon_for_app_id(app_id, friendly=""):
    """The icon of a running application.

    The id of a window and the id of a desktop entry do not always
    agree, so the friendly name of the application is tried as well.
    """
    found = icon_for_app(app_id)
    if found:
        return found
    if friendly:
        return icon_for_app(friendly)
    return None


def search(text, limit=40, show_all=False):
    """Applications matching a search string."""
    source = all_applications() if show_all else applications()
    if not text:
        return source[:limit]
    needle = text.lower()
    hits = [app for app in source if needle in app["name"].lower()]
    hits.sort(key=lambda app: (not app["name"].lower().startswith(needle),
                                len(app["name"])))
    return hits[:limit]
