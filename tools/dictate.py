"""Dictation: record, listen for the silence, transcribe, type.

The button only has to start this; the take stops itself a breath
after the speaking stops.  A second click on the button interrupts
the take through SIGINT, and the same transcription runs then too.

The recorder is pw-record, the reader is the wav it grows, the
transcriber is the same whisper wrapper the rest of the shell uses.
"""

from __future__ import annotations

import os
import signal
import struct
import subprocess
import sys
import time

WAV = "/tmp/dictation.wav"
PID_FILE = "/tmp/dictation.pid"
VOICE = os.path.expanduser("~/venvs/voice/bin/python")
VOICE_STT = os.path.expanduser("~/bin/_voice.py")

SILENCE_AFTER = 1.15      # seconds of quiet that end the take
MIN_TAKE = 0.6            # a take shorter than this is nothing
MAX_TAKE = 60.0           # a stuck recorder never eats the afternoon
CHUNK = 0.10              # how much audio one reading looks at
DEBUG = bool(os.environ.get("MACSHELL_DICTATION_DEBUG"))

_stopping = False


def _notify(title, body, timeout_ms):
    subprocess.Popen(
        ["notify-send", "-a", "Dictation", title, body, "-t", str(timeout_ms)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _data_offset(path):
    """Where the samples start: the data chunk of the wav header."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return None
    spot = head.find(b"data")
    return spot + 8 if spot >= 0 else None


def _tail_rms(path, offset, seconds):
    """RMS of the last `seconds` of the file, in s16 units."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0.0
    want = int(16000 * seconds) * 2
    start = max(offset, size - want)
    if size - start < 320:
        return 0.0
    try:
        with open(path, "rb") as fh:
            fh.seek(start)
            raw = fh.read(want)
    except OSError:
        return 0.0
    count = len(raw) // 2
    if not count:
        return 0.0
    samples = struct.unpack("<%dh" % count, raw[:count * 2])
    return (sum(v * v for v in samples) / count) ** 0.5


def _stop_recorder(recorder):
    try:
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=4)
    except Exception:
        try:
            recorder.kill()
        except Exception:
            pass


def _transcribe():
    try:
        result = subprocess.run(
            [VOICE, VOICE_STT, "stt", WAV, "--language", "en",
             "--model", "base"],
            capture_output=True, text=True, timeout=90)
        text = (result.stdout or "").strip()
    except Exception:
        text = ""
    if not text:
        _notify("Dictation", "Nothing was said.", 4000)
        return
    _notify("Dictation", "Done.", 2000)
    if os.environ.get("MACSHELL_DICTATION_NO_TYPE"):
        return
    try:
        subprocess.run(["wtype", "-"], input=text, text=True, timeout=10)
    except Exception:
        pass


def main():
    global _stopping

    def on_signal(_signum, _frame):
        global _stopping
        _stopping = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # the same sane hardware gain the shell asks for before a take
    try:
        out = subprocess.run(["amixer", "-c0", "sget", "Capture"],
                             capture_output=True, text=True, timeout=2).stdout
        for line in out.splitlines():
            if "Front Left: Capture" in line:
                value = int(line.split("Capture")[1].split()[0])
                if value > 35:
                    subprocess.run(["amixer", "-c0", "sset", "Capture", "25"],
                                   capture_output=True, timeout=2)
                break
    except Exception:
        pass

    try:
        os.unlink(WAV)
    except OSError:
        pass
    recorder = subprocess.Popen(
        ["pw-record", "--rate", "16000", "--channels", "1", WAV],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(PID_FILE, "w") as fh:
        fh.write(str(os.getpid()))

    started = time.monotonic()
    offset = None
    noise = None
    samples = []
    spoke = False
    quiet_for = 0.0
    last_size = 0

    while not _stopping:
        time.sleep(CHUNK)
        if recorder.poll() is not None:
            break
        if offset is None:
            offset = _data_offset(WAV)
            continue
        try:
            size = os.path.getsize(WAV)
        except OSError:
            size = last_size
        if size <= last_size:
            continue
        last_size = size
        rms = _tail_rms(WAV, offset, CHUNK)
        elapsed = time.monotonic() - started
        if noise is None:
            # the first half second is the room, not the voice; a single
            # loud transient (the notification of the take itself) must
            # not lift the floor, so the quietest third is the room
            if elapsed < 0.55:
                samples.append(rms)
                continue
            if samples:
                ordered = sorted(samples)
                noise = ordered[len(ordered) // 3]
            else:
                noise = 0.0
            # the card is announced only once the room is known, so the
            # announcement cannot be mistaken for the room
            _notify("Dictation", "Recording — speak now; it stops on its "
                    "own.", 4000)
        threshold = min(max(240.0, (noise or 0.0) * 2.2), 900.0)
        if DEBUG:
            print(f"t={elapsed:5.2f} rms={rms:8.1f} thr={threshold:7.1f} "
                  f"spoke={int(spoke)} quiet={quiet_for:4.2f}", flush=True)
        if rms > threshold:
            spoke = True
            quiet_for = 0.0
        elif spoke:
            quiet_for += CHUNK
        if spoke and quiet_for >= SILENCE_AFTER:
            break
        if elapsed > MAX_TAKE:
            break

    _stop_recorder(recorder)
    elapsed = time.monotonic() - started
    if elapsed < MIN_TAKE:
        try:
            os.unlink(PID_FILE)
        except OSError:
            pass
        _notify("Dictation", "Nothing was said.", 4000)
        return 0
    _notify("Dictation", "Transcribing…", 8000)
    _transcribe()
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
