"""Screen recording, the macOS way.

A toggle: the first call asks for a region with slurp and starts
wf-recorder on it; the second call ends the take and tells where the
file went.  The pid and the path live in /tmp, so the shell can be
restarted without losing the recording.
"""

from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import sys
import time

CONFIG = os.path.expanduser("~/.config/macshell/config.json")
PID_FILE = "/tmp/macshell-record.pid"
LOCK_FILE = "/tmp/macshell-record.lock"
PATH_FILE = "/tmp/macshell-record.path"
START_FILE = "/tmp/macshell-record.start"
VIDEOS = os.path.expanduser("~/Videos")


def _notify(title, body, timeout_ms=4000):
    subprocess.Popen(
        ["notify-send", "-a", "Screen recording", title, body,
         "-t", str(timeout_ms)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pid():
    try:
        with open(PID_FILE) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def recording():
    pid = _pid()
    return bool(pid and os.path.exists(f"/proc/{pid}"))


def _audio_args():
    """The audio flag for the take, from `record_audio` in config.json.

    false (the default) records the picture alone; "mic" takes the
    microphone; "system" takes the monitor of the default output, so the
    sound of the programs lands in the file without a speaker in the
    room.  Both were tried with wf-recorder on this machine: each writes
    an aac stream beside the h264 one.
    """
    try:
        with open(CONFIG) as fh:
            choice = json.load(fh).get("record_audio", False)
    except (OSError, ValueError):
        return []
    if not choice:
        return []
    if choice in ("system", "output", "monitor"):
        try:
            sink = subprocess.run(["pactl", "get-default-sink"],
                                  capture_output=True, text=True,
                                  timeout=2).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            sink = ""
        if sink:
            return [f"--audio={sink}.monitor"]
        return []
    if choice in (True, "mic", "microphone", "input"):
        return ["--audio"]
    return []


def start():
    geo = ""
    try:
        geo = subprocess.run(["slurp"], capture_output=True, text=True,
                             timeout=120).stdout.strip()
    except Exception:
        geo = ""
    if not geo:
        return 1
    os.makedirs(VIDEOS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(VIDEOS, f"Recording_{stamp}.mp4")
    command = ["wf-recorder", "-f", path, "-g", geo, *_audio_args()]
    try:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except OSError as exc:
        _notify("Screen recording", f"wf-recorder would not start: {exc}")
        return 1
    with open(PID_FILE, "w") as fh:
        fh.write(str(proc.pid))
    with open(PATH_FILE, "w") as fh:
        fh.write(path)
    with open(START_FILE, "w") as fh:
        fh.write(f"{time.time():.3f}")
    _notify("Screen recording",
            "Recording the area — press again to stop.", 4000)
    return 0


def stop():
    pid = _pid()
    path = ""
    try:
        with open(PATH_FILE) as fh:
            path = fh.read().strip()
    except OSError:
        path = ""
    if pid and os.path.exists(f"/proc/{pid}"):
        try:
            os.kill(pid, signal.SIGINT)
        except OSError:
            pass
        # wf-recorder needs a moment to close the file well
        for _ in range(40):
            if not os.path.exists(f"/proc/{pid}"):
                break
            time.sleep(0.1)
    for name in (PID_FILE, PATH_FILE, START_FILE):
        try:
            os.unlink(name)
        except OSError:
            pass
    if path and os.path.exists(path):
        _notify("Screen recording", f"Saved {path}", 6000)
        preview = os.path.expanduser("~/.config/river/shotpreview.py")
        if os.path.exists(preview):
            try:
                subprocess.Popen([sys.executable, preview, path],
                                 start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError:
                pass
    else:
        _notify("Screen recording", "The take did not save.")
    return 0


def _take_lock():
    """One slurp at a time: a double toggle must not stack two of them."""
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            with open(LOCK_FILE) as fh:
                pid = int(fh.read().strip())
            if not os.path.exists(f"/proc/{pid}"):
                os.unlink(LOCK_FILE)
                return _take_lock()
        except (OSError, ValueError):
            pass
        return False


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        return stop()
    if recording():
        return stop()
    if not _take_lock():
        return 0
    try:
        return start()
    finally:
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
