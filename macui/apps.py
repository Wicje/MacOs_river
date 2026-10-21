"""The installed applications.

The desktop entries are parsed once and cached; the icons are looked up in
the usual icon directories.
"""

from __future__ import annotations

import os
import re

DESKTOP_DIRS = (
    "~/.local/share/applications",
    "/usr/share/applications",
    "/usr/local/share/applications",
)

ICON_SIZES = ("128x128", "64x64", "48x48", "256x256", "96x96", "32x32")
ICON_DIRS = (
    "~/.local/share/icons",
    "/usr/share/icons",
    "/usr/share/pixmaps",
)

_cache = None

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
    """Strip the field codes desktop files use."""
    command = re.sub(r"%[fFuUdDnNickvm]", "", command)
    command = command.replace("\\\\", "\\")
    return " ".join(command.split())


def icon_path(name):
    """Find the icon file for a desktop entry."""
    if not name:
        return None
    if os.path.isabs(name) and os.path.exists(name):
        return name
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


def icon_for_app(name):
    """The icon of a desktop entry, by its name or by its id.

    The icon of a program is often a path of its own (an AppImage draws
    its icon from the file), so the desktop entry is asked first and the
    icon theme second.
    """
    if not name:
        return None
    key = name.lower()
    for entry in _read_entries(block=False):
        if key in (entry["id"].lower(), entry["name"].lower()):
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
            }
    for app in entries.values():
        if app["id"] == "gimp":
            app["name"] = "GIMP"
        elif app["id"] == "mpv":
            app["name"] = "mpv"
    return sorted(entries.values(), key=lambda item: item["name"].lower())


def applications():
    """The applications that belong in the application grid."""
    global _cache
    if _cache is None:
        _cache = _read_entries(block=True)
    return _cache


def all_applications():
    """Every entry, including the settings tools and helpers."""
    return _read_entries(block=False)


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
