"""System state readers shared by the shell panels.

Everything that needs an external program runs in a background thread, so
the shell's main loop never waits for a slow command and the panels stay
responsive while the state is refreshed.
"""

from __future__ import annotations

import glob
import json
import os
import signal
import subprocess
import threading
import time

from . import apps

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
    "recent": [],
    "weather": "",
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
    if "performance" in out:
        return "performance"
    if "power-saver" in out:
        return "power-saver"
    return "balanced"


def set_power_mode(mode):
    """Switch the power profile; the menu bar shows the one it sits in."""
    if mode not in ("performance", "balanced", "power-saver"):
        return
    spawn(f"powerprofilesctl set {mode}")
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
    """Switch to a focus mode.

    The hour the mode began is written down, so the focus timer of the
    widget column knows how long the session has been.
    """
    if mode and mode != "off":
        try:
            with open(FOCUS_FILE, "w") as fh:
                fh.write(str(time.time()))
        except OSError:
            pass
    else:
        try:
            os.unlink(FOCUS_FILE)
        except OSError:
            pass
    spawn(f"makoctl mode -t {mode}")


def toggle_dnd():
    spawn("makoctl mode -t do-not-disturb")


# --- the dictation button ---------------------------------------------------

DICTATION_PID = "/tmp/dictation.pid"
DICTATION_WAV = "/tmp/dictation.wav"
_VOICE = f"{os.path.expanduser('~')}/venvs/voice/bin/python"
_VOICE_STT = f"{os.path.expanduser('~')}/bin/_voice.py"


def dictation_active():
    """Whether the microphone is recording for the dictation button."""
    try:
        with open(DICTATION_PID) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return b"pw-record" in fh.read()
    except OSError:
        return False


def toggle_dictation():
    """Start the microphone, and stop it by typing what was said."""
    if dictation_active():
        try:
            with open(DICTATION_PID) as fh:
                pid = int(fh.read().strip())
            os.kill(pid, signal.SIGINT)
        except (OSError, ValueError):
            pass
        spawn(f'sh -c text=$("{_VOICE}" "{_VOICE_STT}" stt "{DICTATION_WAV}" '
              '--language en --model base 2>/dev/null); '
              'notify-send -a Dictation "Dictation" "Transcribing…" '
              f'-t 8000 2>/dev/null; [ -n "$text" ] && '
              'notify-send -a Dictation "Dictation" "Done." -t 2000 '
              '2>/dev/null; '
              f'[ -n "$text" ] && printf "%s" "$text" | wtype -')
    else:
        spawn(f"sh -c 'pw-record --rate 16000 --channels 1 "
              f"{DICTATION_WAV} & echo $! > {DICTATION_PID}'; "
              "sleep 1; notify-send -a Dictation 'Dictation' "
              "'Recording — speak now, click again to stop' -t 4000")


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

    Returns True when a window was found and activated.  The work happens
    in a thread, so the panel that asked for it keeps drawing.
    """
    app_id = (app_id or "").lower()
    if not app_id:
        return False
    for entry in toplevels():
        if (entry.get("app_id") or "").lower() == app_id:
            title = entry.get("title") or ""
            if not title:
                return False
            return raise_window(title)
    return False


def raise_window(title):
    """Raise a window by its title.

    The helper talks to the compositor, which takes a moment, so the work
    happens in a thread: the panels must not wait for it.
    """
    title = (title or "").strip()
    if not title:
        return False

    def work():
        try:
            subprocess.run(
                [os.path.expanduser("~/.local/bin/macshell-toplevels"),
                 "--activate", title],
                capture_output=True, timeout=8)
        except (OSError, subprocess.SubprocessError):
            pass

    threading.Thread(target=work, daemon=True).start()
    return True


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


_friendly_cache = {}
_friendly_time = 0.0


def friendly_name(app_id):
    """A readable name for an application id.

    The compositor calls the applications by their own name, which is
    not always the name the desktop knows them by, so the desktop files
    are asked as well.  The answers are kept for a while: the dock asks
    for them on every frame.
    """
    global _friendly_time
    if not app_id:
        return ""
    now = time.monotonic()
    if now - _friendly_time > apps.CACHE_TTL:
        _friendly_cache.clear()
        _friendly_time = now
    if app_id in _friendly_cache:
        return _friendly_cache[app_id]
    if app_id in FRIENDLY_NAMES:
        name = FRIENDLY_NAMES[app_id]
    else:
        name = apps.name_for_id(app_id) or app_id
    _friendly_cache[app_id] = name
    return name


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

def _track_recent(app_id):
    """Remember the applications that were in front, the newest first."""
    key = (app_id or "").lower()
    if not key:
        return
    with _cache_lock:
        recent = list(_cache.get("recent") or [])
    if recent and recent[0] == key:
        return
    recent = [key] + [item for item in recent if item != key]
    with _cache_lock:
        _cache["recent"] = recent[:6]


def recent_apps():
    """The applications that were in front, the newest first."""
    with _cache_lock:
        return list(_cache.get("recent") or [])


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
    _track_recent(app_id)
    weather = _fetch_weather()
    with _cache_lock:
        if clip is not None:
            _cache["clipboard"] = clip
            _cache["clip_id"] = clip["id"]
        if weather:
            _cache["weather"] = weather
            _cache["weather_full"] = _read_weather_json()
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


WEATHER_FILE = "/tmp/macshell-weather"
WEATHER_JSON = "/tmp/macshell-weather.json"
WEATHER_MAX_AGE = 1800


def _weather_from_j1(data):
    """The wttr.in JSON turned into the shell's own report."""
    try:
        now = data["current_condition"][0]
        condition = now["weatherDesc"][0]["value"]
        report = {
            "place": (data.get("nearest_area") or [{}])[0].get("areaName",
                                                                [{}])[0]
            .get("value", ""),
            "condition": condition,
            "temp": now.get("temp_C", ""),
            "feels": now.get("FeelsLikeC", ""),
            "min": data["weather"][0].get("mintempC", ""),
            "max": data["weather"][0].get("maxtempC", ""),
            "humid": now.get("humidity", ""),
            "wind": now.get("windspeedKmph", ""),
        }
        days = []
        for index, day in enumerate(data.get("weather", [])[:5]):
            if index == 0:
                continue
            icons = [h["weatherDesc"][0]["value"] for h in day.get("hourly", [{}])]
            days.append({
                "dow": time.strftime("%a", time.strptime(day["date"],
                                                        "%Y-%m-%d")),
                "min": day.get("mintempC", ""),
                "max": day.get("maxtempC", ""),
                "condition": icons[len(icons) // 2] if icons else "",
            })
        report["forecast"] = days
        return report
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _fetch_weather():
    """Ask wttr.in for the weather, and remember it for half an hour.

    The answer is kept twice: the short line the dock and the widgets
    have always shown, and the whole report with the forecast of the
    next days for the widget column and the notification centre.
    """
    import time as _time

    try:
        age = _time.time() - os.path.getmtime(WEATHER_JSON)
        if age < WEATHER_MAX_AGE:
            with open(WEATHER_FILE, encoding="utf-8") as fh:
                return fh.read().strip()
    except OSError:
        pass
    out = run("curl -s --max-time 8 'wttr.in/?format=j1'")
    if not out.strip():
        return ""
    try:
        data = json.loads(out)
    except ValueError:
        data = None
    report = _weather_from_j1(data) if data else None
    if not report:
        return ""
    short = f"{report['place']}: {report['condition']} " \
            f"+{report['temp']}C"
    try:
        with open(WEATHER_FILE, "w", encoding="utf-8") as fh:
            fh.write(short)
        with open(WEATHER_JSON, "w", encoding="utf-8") as fh:
            json.dump(report, fh)
    except OSError:
        pass
    return short


def weather_report():
    """The whole weather report, forecast and all.

    It comes from the file of the last two hours, so the widgets of a
    morning that started with no network at all still have yesterday's
    report to show.
    """
    report = _read_weather_json(WEATHER_MAX_AGE * 4)
    if report:
        return report
    with _cache_lock:
        return None


def _read_weather_json(max_age=None):
    """The report of the last fetch, if the file is fresh enough."""
    try:
        age = time.time() - os.path.getmtime(WEATHER_JSON)
        if max_age is not None and age > max_age:
            return None
        with open(WEATHER_JSON, encoding="utf-8") as fh:
            report = json.load(fh)
        if isinstance(report, dict) and report.get("temp"):
            return report
    except (OSError, ValueError):
        pass
    return None


def weather():
    """The weather of the place the machine is in."""
    with _cache_lock:
        return _cache.get("weather") or ""


# --- the lights of the notch ------------------------------------------------
#
# macOS shows a green dot when a program uses the camera and an orange
# one when a program uses the microphone.  The lights live in the
# kernel: a capture device that runs is a file that says so.

def mic_active():
    """True when a program is recording from the microphone."""
    active = False
    try:
        for sub in glob.glob("/proc/asound/*/pcm*c/sub*/status"):
            with open(sub) as fh:
                if "RUNNING" in fh.read():
                    active = True
                    break
    except OSError:
        pass
    with _cache_lock:
        _cache["mic"] = active
    return active


def camera_active():
    """True when a program holds a camera.

    A camera nobody holds answers reads; one that a program is
    streaming from is owned by that program, and fuser sees the name.
    """
    try:
        out = subprocess.run(["fuser", "/dev/video0"],
                             capture_output=True, text=True, timeout=3)
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


# --- the island: activities -------------------------------------------------
#
# The Dynamic Island shows whatever is happening now, and the strongest
# activity wins.  These live in a small file that any program on the desk
# can write, the same way macOS apps publish to the island.

ACTIVITY_FILE = "/tmp/macshell-activity.json"
_PRIORITIES = ("background", "low", "normal", "high", "critical")


def activities():
    """The activities of the island, strongest first.

    Every entry carries id, title, detail, progress (0 to 1), priority and
    an optional expires epoch, past which the entry no longer shows
    however nothing prunes it early.
    """
    data = None
    try:
        with open(ACTIVITY_FILE) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    now = time.time()
    rows = []
    for entry in (data or {}).get("items") or []:
        if not isinstance(entry, dict):
            continue
        expires = entry.get("expires")
        if isinstance(expires, (int, float)) and expires <= now:
            continue
        priority = entry.get("priority") or "normal"
        if priority not in _PRIORITIES:
            priority = "normal"
        rows.append(entry)
    rows.sort(key=lambda row: _PRIORITIES.index(row["priority"]),
              reverse=True)
    return rows


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


# --- the development widget -------------------------------------------------

FOCUS_FILE = "/tmp/macshell-focus-start"


def dev_project(path):
    """The state of the project's git, for the dev widget.

    (branch, dirty count, and how long ago the last commit was made) —
    the whole thing fails quietly, so a folder that is not a repository
    shows an honest empty row.
    """
    if not path:
        return "", 0, 0.0
    try:
        out = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            capture_output=True, text=True, timeout=3)
        branch = out.stdout.strip()
        out = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True, timeout=3)
        dirty = len([line for line in out.stdout.splitlines()
                     if line.strip()])
        out = subprocess.run(
            ["git", "-C", path, "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=3)
        stamp = float(out.stdout.strip() or 0)
        age = max(0.0, time.time() - stamp) if stamp else 0.0
        return branch, dirty, age
    except (OSError, subprocess.SubprocessError, ValueError):
        return "", 0, 0.0


def focus_started():
    """When the present focus mode began (None when it is off)."""
    try:
        with open(FOCUS_FILE) as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return None


def focus_minutes():
    """How long the focus mode has been on, in minutes."""
    started = focus_started()
    if started is None:
        return 0
    return int((time.time() - started) / 60.0)
