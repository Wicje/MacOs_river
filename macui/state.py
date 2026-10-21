"""System state readers shared by the shell panels.

Everything that needs an external program runs in a background thread, so
the shell's main loop never waits for a slow command and the panels stay
responsive while the state is refreshed.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time

CACHE = "/tmp/macshell-state"
THEME_FILE = os.path.expanduser("~/.config/macshell/.theme")

# Values are refreshed in the background and read from here by the panels.
_cache = {
    "media": None,
    "app": "Finder",
    "app_id": "",
    "window": "",
    "running": set(),
    "toplevels": [],
    "screentime": None,
    "clipboard": None,
    "clip_id": "",
}
_cache_lock = threading.Lock()


def run(cmd, timeout=3):
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
    except Exception:
        return ""


def spawn(cmd):
    subprocess.Popen(cmd, shell=True, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_json(cmd):
    out = run(cmd)
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


# --- network ---------------------------------------------------------------

def wifi_enabled():
    return run("nmcli -t -f WIFI general") == "enabled"


def wifi_ssid():
    out = run("nmcli -t -f ACTIVE,SSID device wifi")
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line.split(":", 1)[1]
    return ""


def wifi_strength():
    out = run("nmcli -t -f SIGNAL device wifi")
    for line in out.splitlines():
        if ":" in line:
            try:
                return int(line.split(":")[1])
            except ValueError:
                pass
    return 0


def toggle_wifi():
    """Turn the wireless radio on or off.

    The card's rfkill switch is often soft blocked, which makes nmcli
    refuse the change, so the block is lifted first.
    """
    if wifi_enabled():
        spawn("nmcli radio wifi off")
    else:
        spawn("rfkill unblock wifi")
        spawn("nmcli radio wifi on")


# --- bluetooth -------------------------------------------------------------

def bluetooth_on():
    return "Powered: yes" in run("bluetoothctl show")


def toggle_bluetooth():
    spawn("bluetoothctl power " + ("off" if bluetooth_on() else "on"))


# --- audio -----------------------------------------------------------------

def volume():
    out = run("wpctl get-volume @DEFAULT_AUDIO_SINK@")
    for token in out.split():
        try:
            return int(round(float(token) * 100))
        except ValueError:
            continue
    return 0


def set_volume(value):
    spawn(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {int(value)}%")


def muted():
    return "MUTED" in run("wpctl get-volume @DEFAULT_AUDIO_SINK@").upper()


def toggle_mute():
    spawn("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")


# --- brightness ------------------------------------------------------------

def brightness():
    cur, mx = run("brightnessctl get"), run("brightnessctl max")
    try:
        return int(round(int(cur) / int(mx) * 100))
    except (ValueError, ZeroDivisionError):
        return 0


def set_brightness(value):
    spawn(f"brightnessctl set {int(value)}%")


# --- focus / do not disturb ------------------------------------------------

def dnd_on():
    return dnd_mode() == "do-not-disturb"


def power_mode():
    """The power profile the machine is running in."""
    out = run("powerprofilesctl get")
    if "power-saver" in out:
        return "power-saver"
    if "performance" in out:
        return "performance"
    return "balanced"


def battery_level():
    """The battery charge in percent, or None."""
    for name in ("BAT0", "BAT1"):
        try:
            with open(f"/sys/class/power_supply/{name}/capacity") as fh:
                return int(fh.read().strip())
        except (OSError, ValueError):
            continue
    return None


def battery_charging():
    try:
        with open("/sys/class/power_supply/BAT0/status") as fh:
            return "Charging" in fh.read()
    except OSError:
        return False


def dnd_mode():
    """The focus mode mako is in."""
    out = run("makoctl mode")
    for mode in ("do-not-disturb", "work", "personal", "sleep"):
        if mode in out:
            return mode
    return "off"


def set_dnd_mode(mode):
    """Switch to a focus mode."""
    spawn(f"makoctl mode -t {mode}")


def toggle_dnd():
    spawn("makoctl mode -t do-not-disturb")


def theme_name():
    try:
        with open(THEME_FILE) as fh:
            return fh.read().strip() or "dark"
    except OSError:
        return "dark"


def toggle_theme():
    """Switch between the light and dark palettes.

    The theme is written to the shell's own config file; the shell reloads
    it once a second, so the change shows up without a restart.
    """
    new = "light" if theme_name() == "dark" else "dark"
    try:
        with open(THEME_FILE, "w") as fh:
            fh.write(new)
    except OSError:
        pass
    # the helper updates the shell's config and the other tools' styles
    spawn(f"{os.path.expanduser('~/.config/river/theme-apply.sh')}")
    spawn("gsettings set org.gnome.desktop.interface color-scheme "
          + ("'prefer-dark'" if new == "dark" else "'default'"))
    return new


# --- media -----------------------------------------------------------------

def _read_media():
    """Ask playerctl what is playing (slow, runs in the background)."""
    if not run("playerctl status"):
        return None
    title = run("playerctl metadata xesam:title")
    if not title:
        return None
    artist = run("playerctl metadata xesam:artist")
    status = run("playerctl status")
    pos = run("playerctl position")
    length = run("playerctl metadata mpris:length")
    art = run("playerctl metadata mpris:artUrl")
    try:
        position = float(pos)
    except ValueError:
        position = 0.0
    try:
        total = float(length) / 1_000_000.0
    except ValueError:
        total = 0.0
    return title, artist, status, position, total, art


def now_playing():
    """Return (title, artist, status, position, length, art_url)."""
    with _cache_lock:
        return _cache["media"]


# --- focused window --------------------------------------------------------

TOPLEVELS = os.path.expanduser("~/.local/bin/macshell-toplevels")


def _toplevels():
    """The compositor's toplevels as a list of dicts.

    River Classic has no introspection command in riverctl, so the shell
    uses the small helper that talks the wlr-foreign-toplevel protocol.
    """
    try:
        out = subprocess.run([TOPLEVELS], capture_output=True, text=True,
                             timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return []
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def focused_window():
    """Return the title of the focused window."""
    with _cache_lock:
        return _cache["window"]


def toplevels():
    """The compositor's toplevels, as the background thread saw them."""
    with _cache_lock:
        return list(_cache["toplevels"])


def running_app_ids():
    """App identifiers of every window that is currently mapped."""
    with _cache_lock:
        return set(_cache["running"])


def window_list():
    """[(app_id, title)] for every open window."""
    out = []
    for entry in _toplevels():
        out.append((entry.get("app_id") or "", entry.get("title") or ""))
    return out


def activate_app(app_id):
    """Bring the window of an application to the front.

    Returns True when a window was found and activated.
    """
    app_id = (app_id or "").lower()
    if not app_id:
        return False
    for entry in _toplevels():
        if (entry.get("app_id") or "").lower() == app_id:
            title = entry.get("title") or ""
            if not title:
                return False
            try:
                subprocess.run(
                    [os.path.expanduser("~/.local/bin/macshell-toplevels"),
                     "--activate", title],
                    capture_output=True, timeout=5)
            except (OSError, subprocess.SubprocessError):
                return False
            return True
    return False


FRIENDLY_NAMES = {
    "foot": "Terminal",
    "footclient": "Terminal",
    "alacritty": "Terminal",
    "kitty": "Terminal",
    "code": "Visual Studio Code",
    "code-oss": "Visual Studio Code",
    "codium": "VSCodium",
    "chromium": "Chromium",
    "chromium-browser": "Chromium",
    "google-chrome": "Google Chrome",
    "firefox": "Firefox",
    "firefox-esr": "Firefox",
    "org.mozilla.firefox": "Firefox",
    "dolphin": "Files",
    "org.kde.dolphin": "Files",
    "gimp": "GIMP",
    "org.gimp.GIMP": "GIMP",
    "mpv": "mpv",
    "vlc": "VLC",
    "org.videolan.VLC": "VLC",
    "audacity": "Audacity",
    "obs": "OBS Studio",
    "com.obsproject.Studio": "OBS Studio",
    "spotify": "Spotify",
    "com.spotify.Client": "Spotify",
    "steam": "Steam",
    "steamwebhelper": "Steam",
    "thunderbird": "Mail",
    "discord": "Discord",
    "zoom": "Zoom",
    "Element": "Element",
}


def focused_app_id():
    """The app id of the focused window, e.g. ``foot``."""
    with _cache_lock:
        return _cache["app_id"]


def focused_app():
    """Human readable name of the focused application."""
    with _cache_lock:
        app_id = _cache["app_id"]
        title = _cache["window"]
    if not app_id:
        return "Finder"
    if app_id in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[app_id]
    # Window titles are usually "App — Document"; the app is the first word.
    for sep in (" — ", " - ", " – "):
        if sep in title:
            title = title.split(sep, 0)[0]
    title = title.strip()
    return title or "Finder"


# --- background refresh ----------------------------------------------------
#
# Reading the state means running playerctl and the toplevel helper, which
# takes a few hundred milliseconds.  Doing that on the main thread made the
# panels feel sluggish, so a background thread keeps the values fresh.

def _read_clipboard():
    """The last thing that was copied.

    The text comes from the clipboard history, the picture from the
    clipboard itself.  Nothing is written down: it only lives as long as
    the shell does.
    """
    out = run("cliphist list")
    first = out.splitlines()[0] if out else ""
    entry_id, _, text = first.partition("\t")
    if not entry_id:
        return None
    if _cache.get("clip_id") == entry_id:
        return None
    image = None
    types = run("wl-paste --list-types")
    if "image/png" in types:
        try:
            data = subprocess.run(["wl-paste", "--type", "image/png"],
                                  capture_output=True, timeout=4).stdout
        except (OSError, subprocess.SubprocessError):
            data = b""
        if data:
            path = "/tmp/macshell-clipboard.png"
            try:
                with open(path, "wb") as fh:
                    fh.write(data)
                image = path
            except OSError:
                image = None
    return {"id": entry_id, "text": text.strip(), "image": image,
            "at": time.time()}


def clipboard():
    """The last thing that was copied, with the time it happened."""
    with _cache_lock:
        return dict(_cache.get("clipboard") or {})


def _refresh_once():
    media = _read_media()
    clip = _read_clipboard()
    entries = _toplevels()
    app_id = ""
    title = ""
    running = set()
    for entry in entries:
        entry_id = (entry.get("app_id") or "").lower()
        if entry_id:
            running.add(entry_id)
        if entry.get("activated") and not app_id:
            app_id = entry.get("app_id") or ""
            title = entry.get("title") or ""
    _track_screen_time(app_id)
    with _cache_lock:
        if clip is not None:
            _cache["clipboard"] = clip
            _cache["clip_id"] = clip["id"]
        _cache["media"] = media
        _cache["app_id"] = app_id
        _cache["window"] = title
        _cache["running"] = running
        _cache["toplevels"] = entries


# --- screen time ------------------------------------------------------------
#
# macOS shows how long every application was in the foreground.  The shell
# knows the same thing: the helper reports the focused window, so the time
# is counted here and kept for the day.

SCREEN_TIME_FILE = os.path.expanduser("~/.local/state/macshell/screentime.json")
_screen_time = {}


def _track_screen_time(app_id):
    """Count the time an application was in the foreground."""
    key = (app_id or "").lower()
    if not key:
        return
    today = time.strftime("%Y-%m-%d")
    try:
        with _cache_lock:
            data = dict(_cache.get("screentime") or {})
    except Exception:  # noqa: BLE001
        data = {}
    if data.get("day") != today:
        data = {"day": today, "apps": {}}
    apps = data.setdefault("apps", {})
    apps[key] = apps.get(key, 0) + 1
    with _cache_lock:
        _cache["screentime"] = data
    _screen_time[key] = True
    # the file is written now and then, not every second
    if sum(apps.values()) % 30 < 1:
        try:
            os.makedirs(os.path.dirname(SCREEN_TIME_FILE), exist_ok=True)
            with open(SCREEN_TIME_FILE, "w") as fh:
                json.dump(data, fh, indent=2)
        except OSError:
            pass


def screen_time():
    """The minutes every application was in the foreground today."""
    today = time.strftime("%Y-%m-%d")
    data = {}
    try:
        with open(SCREEN_TIME_FILE) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    if data.get("day") != today:
        data = {"day": today, "apps": {}}
    with _cache_lock:
        data = dict(_cache.get("screentime") or data)
    if data.get("day") != today:
        return []
    apps = data.get("apps") or {}
    rows = [(name, round(seconds / 60.0)) for name, seconds in apps.items()]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows[:5]


def _refresh_loop():
    while True:
        try:
            _refresh_once()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)


def start_refresher():
    """Start the background thread that keeps the cache fresh."""
    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
    return thread
