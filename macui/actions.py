"""Actions the shell can perform on the desktop.

Everything here works on both River and Sway/SwayFX: the compositor is
detected at call time and the appropriate command is used.  River Classic
renamed a few commands compared to upstream river (``close`` instead of
``close-view``), so the ones that differ are looked up in the installed
completion file before they are used.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

from . import state

HOME = os.path.expanduser("~")

_RIVER_COMMANDS = None


def _sway():
    return subprocess.run(["swaymsg", "-r", "get_tree"], capture_output=True,
                          text=True, timeout=2).stdout.strip()


def _river():
    return subprocess.run(["riverctl", "get-focused-view"], capture_output=True,
                          text=True, timeout=2).stdout.strip()


def is_sway():
    try:
        return bool(subprocess.run(["which", "swaymsg"], capture_output=True,
                                    timeout=2).stdout.strip())
    except Exception:
        return False


def river_commands():
    """The commands this installation's riverctl understands."""
    global _RIVER_COMMANDS
    if _RIVER_COMMANDS is None:
        names = set()
        paths = (
            "/usr/share/bash-completion/completions/riverctl",
            "/usr/share/fish/vendor_completions.d/riverctl.fish",
        )
        for path in paths:
            try:
                with open(path) as fh:
                    text = fh.read()
            except OSError:
                continue
            for block in re.findall(r'OPTS="([^"]*)"', text):
                names.update(t for t in block.split() if t and t != "\\")
            names.update(re.findall(r"-c (\S+)", text))
        _RIVER_COMMANDS = names
    return _RIVER_COMMANDS


def river_cmd(*candidates):
    """The first candidate command the installed riverctl knows."""
    known = river_commands()
    for candidate in candidates:
        if candidate in known:
            return candidate
    return candidates[0]


def _run(cmd):
    subprocess.Popen(cmd, shell=True, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- windows ----------------------------------------------------------------

def close_window():
    if is_sway():
        _run("swaymsg kill")
    else:
        _run(f"riverctl {river_cmd('close', 'close-view')}")


def minimize_window():
    """Move the focused window into the scratchpad / hidden tag."""
    if is_sway():
        _run("swaymsg move container to scratchpad")
    else:
        _run("riverctl set-view-tags 2147483648")


def restore_window():
    if is_sway():
        _run("swaymsg scratchpad show")
    else:
        _run("riverctl set-focused-tags 2147483648")


def toggle_fullscreen():
    if is_sway():
        _run("swaymsg fullscreen toggle")
    else:
        _run("riverctl toggle-fullscreen")


def bring_to_front():
    if is_sway():
        _run("swaymsg focus container")
    else:
        _run("riverctl focus-view next")


def move_to_workspace(index):
    if is_sway():
        _run(f"swaymsg move container to workspace {index}")
    else:
        _run(f"riverctl set-view-tags {1 << (index - 1)}")


def move_to_output(direction):
    """Move the focused window to the screen left/right/up/down of it."""
    if is_sway():
        _run(f"swaymsg move container to output {direction}")
    else:
        _run(f"riverctl {river_cmd('send-to-output', 'move-view-to-output')} "
             f"{direction}")


def _screen_size():
    """The size of the output the shell draws on."""
    width, height = 1366, 768
    try:
        out = subprocess.run(["wlr-randr"], capture_output=True, text=True,
                             timeout=3).stdout
        current = False
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Current mode:"):
                current = True
                continue
            if current and "px" in line:
                parts = line.split()
                width = int(parts[0].split("x")[0])
                height = int(parts[2].split("x")[0])
                break
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return width, height


def tile_window(zone="left"):
    """Tile the focused window the way macOS Sequoia does.

    The zones are left, right, top, bottom and the four corners:

        tile:left        the left half
        tile:top-right   the quarter in the top right corner
    """
    if is_sway():
        _run("swaymsg move position 0 0")
        return
    width, height = _screen_size()
    half_w, half_w_gap = width // 2, 0
    half_h = height // 2

    edges = []
    if "left" in zone:
        edges.append("left")
    if "right" in zone:
        edges.append("right")
    if "top" in zone:
        edges.append("top")
    if "bottom" in zone:
        edges.append("bottom")
    for edge in edges:
        _run(f"riverctl snap {edge}")
    if "left" in zone or "right" in zone:
        _run(f"riverctl resize horizontal -{half_w}")
    if "top" in zone or "bottom" in zone:
        _run(f"riverctl resize vertical -{half_h}")


def zoom_window():
    """macOS' Zoom: maximise the focused window inside its container."""
    if is_sway():
        _run("swaymsg 'resize set height 1000 width 1000'")
    else:
        _run(f"riverctl {river_cmd('zoom', 'toggle-fullscreen')}")


# --- system -----------------------------------------------------------------

def new_terminal():
    _run("foot")


def open_file_manager(path=None):
    _run(f"dolphin {path}" if path else "dolphin")


def open_home():
    _run(f"dolphin {HOME}")


def open_computer():
    _run("dolphin /")


def new_files_window():
    _run(f"dolphin {HOME}")


def choose_folder():
    """Ask for a folder and open it in the file manager."""
    _run(f"wofi --show files --dir {HOME}")


def choose_file():
    """Ask for a file and open it with its default application."""
    _run(f"wofi --show files --dir {HOME}")


KEYSYMS = {
    "plus": "plus",
    "minus": "minus",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "space": "space",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "return": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "backspace": "BackSpace",
}

MODIFIERS = {"cmd": "super", "ctrl": "ctrl", "alt": "alt", "shift": "shift"}


def send(combo):
    """Send a key combination to the focused window.

    The spelling follows the macOS menus: ``ctrl+shift+n``.  ``cmd`` is
    accepted as well and maps to the super key.
    """
    parts = combo.split("+")
    key = parts[-1].strip().lower()
    mods = []
    for mod in parts[:-1]:
        name = MODIFIERS.get(mod.strip().lower())
        if name:
            mods.append(name)
    args = ["wtype"]
    for mod in mods:
        args += ["-M", mod]
    args += ["-k", KEYSYMS.get(key, key)]
    _run(" ".join(args))


def copy_selection():
    """Copy the primary selection to the clipboard."""
    _run("wl-paste --primary | wl-copy")


def cut_selection():
    """Copy the primary selection to the clipboard and clear it."""
    _run("wl-paste --primary | wl-copy --clear")


def paste_selection():
    """Paste the clipboard into the focused window."""
    _run("wl-paste --no-newline | wtype -")


def clipboard_copy():
    copy_selection()


def clipboard_paste():
    paste_selection()


def clipboard_cut():
    cut_selection()


def select_all():
    _run("wtype -M ctrl -k a")


def undo():
    _run("wtype -M ctrl -k z")


def redo():
    _run("wtype -M ctrl -k shift -k z")


def lock_session():
    _run("swaylock")


def suspend():
    _run("systemctl suspend")


def reboot():
    _run("systemctl reboot")


def poweroff():
    _run("systemctl poweroff")


def log_out():
    if is_sway():
        _run("swaymsg exit")
    else:
        _run("riverctl exit")


def list_windows():
    """Return [(app_id, title)] for every open window."""
    out = []
    for entry in state._toplevels():
        out.append((entry.get("app_id") or "?", entry.get("title") or ""))
    return out


def activate_window(title):
    """Raise the window whose title contains `title`."""
    try:
        subprocess.run([os.path.expanduser("~/.local/bin/macshell-toplevels"),
                        "--activate", title], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def switch_tag(tag):
    """Switch to a workspace (1-9)."""
    if is_sway():
        _run(f"swaymsg workspace {tag}")
    else:
        _run(f"riverctl set-focused-tags {1 << (tag - 1)}")


def kill_window(title):
    """Close the window whose title contains `title`."""
    try:
        subprocess.run([os.path.expanduser("~/.local/bin/macshell-toplevels"),
                        "--close", title], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


# --- info -------------------------------------------------------------------

def open_store():
    _run("xdg-open https://archlinux.org/packages/")


def open_help():
    _run("xdg-open https://wiki.archlinux.org/title/Main_page")


def open_shortcuts():
    _run("foot -e cat " + HOME + "/.config/sway/config")


def system_info():
    """Facts for the About This Mac panel."""
    info = {
        "model": "Linux PC",
        "os": "Arch Linux",
        "shell": "macOS Tahoe shell",
        "kernel": os.uname().release,
        "compositor": "SwayFX" if is_sway() else "River Classic",
        "cpu": "",
        "memory": "",
        "gpu": "",
        "disk": "",
        "display": "",
        "uptime": "",
    }
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.startswith("model name"):
                    info["cpu"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    info["memory"] = f"{kb / 1024 / 1024:.1f} GB"
                    break
    except (OSError, ValueError):
        pass

    # the graphics card
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True,
                             timeout=3).stdout
        for line in out.splitlines():
            if "VGA compatible controller" in line or "3D controller" in line:
                info["gpu"] = line.split(": ", 1)[-1].split(" (")[0]
                break
    except (OSError, subprocess.SubprocessError):
        pass

    # the root filesystem
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        used = total - stat.f_bavail * stat.f_frsize
        info["disk"] = f"{used / 1e9:.0f} GB of {total / 1e9:.0f} GB"
    except OSError:
        pass

    # the display
    try:
        out = subprocess.run(["wlr-randr"], capture_output=True, text=True,
                             timeout=3).stdout
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Current mode:"):
                mode = stripped.split(":", 1)[1].strip().split()[0]
                info["display"] = mode.replace("x", " × ")
                break
            if "current)" in stripped:
                mode = stripped.split()[0]
                info["display"] = mode.replace("x", " × ")
                break
    except (OSError, subprocess.SubprocessError):
        pass

    # how long the session has been running
    try:
        with open("/proc/uptime") as fh:
            seconds = float(fh.read().split()[0])
        hours, rest = divmod(int(seconds), 3600)
        minutes = rest // 60
        info["uptime"] = f"{hours} h {minutes} min"
    except (OSError, ValueError):
        pass
    return info
