"""The system sounds of the shell: tiny synthesized wavs played with
paplay, the way macOS plays its own set.  Everything is made at first
use: sine prompts, shaped noise and short envelopes — nothing ships
as a file, the machine already has the sound in it."""

import math
import os
import struct
import subprocess

from . import metrics
from . import state

_DIR = "/tmp/macshell-sounds"

# the recipes: (name, seconds, builder)
def _sine_wave(freq, seconds, amp=0.5, decay=None):
    rows = []
    n = int(22050 * seconds)
    for i in range(n):
        t = i / 22050.0
        envelope = 1.0
        if decay is not None:
            envelope = math.exp(-t * decay)
        if t < 0.01:
            envelope *= t / 0.01
        v = math.sin(2 * math.pi * freq * t) * amp * envelope
        rows.append(int(v * 32767))
    return rows


def _chord(freqs, seconds, amp=0.35, decay=4.0):
    rows = []
    n = int(22050 * seconds)
    for i in range(n):
        t = i / 22050.0
        envelope = math.exp(-t * decay)
        if t < 0.02:
            envelope *= t / 0.02
        v = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        rows.append(int(v * amp * envelope * 32767))
    return rows


def _noise(seconds, amp=0.5, decay=18.0, seed=7):
    import random
    rng = random.Random(seed)
    rows = []
    n = int(22050 * seconds)
    last = 0.0
    for i in range(n):
        t = i / 22050.0
        envelope = math.exp(-t * decay)
        last = 0.7 * last + 0.3 * (rng.uniform(-1, 1))
        rows.append(int(last * amp * envelope * 32767))
    return rows


def _pop(seconds=0.16, from_hz=880.0, to_hz=220.0, amp=0.6):
    rows = []
    n = int(22050 * seconds)
    phase = 0.0
    for i in range(n):
        t = i / 22050.0
        freq = from_hz + (to_hz - from_hz) * (t / seconds)
        phase += 2 * math.pi * freq / 22050.0
        envelope = math.exp(-t * 24.0)
        rows.append(int(math.sin(phase) * amp * envelope * 32767))
    return rows


def _writes(name, rows):
    import wave
    os.makedirs(_DIR, exist_ok=True)
    path = os.path.join(_DIR, name + ".wav")
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(22050)
        fh.writeframes(b"".join(struct.pack("<h", v) for v in rows))
    return path


def build():
    """Make every recipe that has not been made yet."""
    os.makedirs(_DIR, exist_ok=True)
    paths = {}
    paths["startup"] = _writes("startup",
                               _chord([196.0, 246.9, 293.7], 1.4, 0.5, 2.2)
                               + _chord([392.0, 493.9, 587.3], 0.3, 0.3, 6.0))
    paths["trash"] = _writes("trash", _noise(0.5, 0.75, 7.0))
    paths["shutter"] = _writes("shutter", _noise(0.09, 0.9, 40.0)
                               + _pop(0.09, 1800.0, 300.0, 0.5))
    paths["pop"] = _writes("pop", _pop())
    paths["tick"] = _writes("tick", _sine_wave(1200.0, 0.05, 0.25, 30.0))
    paths["unlock"] = _writes("unlock",
                              _chord([392.0, 493.9, 587.3], 0.6, 0.4, 5.0))
    paths["battery"] = _writes("battery", _sine_wave(660.0, 0.25, 0.4, 10.0)
                               + _sine_wave(440.0, 0.25, 0.4, 8.0))
    return paths


def _built():
    return dict((name, os.path.join(_DIR, name + ".wav"))
                for name in ("startup", "trash", "shutter", "pop", "tick",
                             "unlock", "battery")
                if os.path.exists(os.path.join(_DIR, name + ".wav")))


def play(name):
    """One of the sounds, at the volume the shell sets for itself."""
    if not os.path.exists(os.path.join(_DIR, name + ".wav")):
        build()
    path = os.path.join(_DIR, name + ".wav")
    if not os.path.exists(path):
        return
    volume = float(metrics.load_config().get("sound_volume", 0.7))
    if metrics.load_config().get("sounds", True) is False or volume <= 0:
        return
    state.spawn(f"paplay --volume={int(max(0.05, min(volume, 1.0)) * 65536)} "
                f"--stream-name macshell {path}")


def startup():
    play("startup")
