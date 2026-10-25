"""The traffic of the machine, the way the meter reads it.

Speeds come straight out of ``/proc/net/dev``: the kernel keeps the
byte counters of every interface, and the difference between two reads
is the traffic of the moment.  The totals of a day, a week or a month
come from small files -- one per day, each holding what passed since
its morning -- kept under ``~/.local/share/macshell/traffic``.  The
meter runs in the background (mstatus-net) and keeps writing the daily
file while the machine is on.
"""

from __future__ import annotations

import os
import time

STORAGE = os.path.expanduser("~/.local/share/macshell/traffic")

_last = None  # (rx_bytes, tx_bytes, epoch) of the previous read
_last_record = None  # the meter keeps its own, for the daily file


def _interfaces():
    names = []
    try:
        with open("/proc/net/dev") as fh:
            for line in fh.readlines()[2:]:
                if ":" in line:
                    names.append(line.split(":")[0].strip())
    except OSError:
        pass
    return names


def interface():
    """The interface that carries the session: Wi-Fi when it exists."""
    try:
        with open("/proc/net/wireless") as fh:
            for line in fh.readlines()[2:]:
                if ":" in line:
                    return line.split(":")[0].strip()
    except OSError:
        pass
    for name in _interfaces():
        if name not in ("lo", "docker0", "zram0") and \
                (name.startswith(("eth", "enp", "wlp", "wlan"))):
            return name
    return None


def counters():
    """The two kernel counters of the chosen interface, or None."""
    name = interface()
    if not name:
        return None
    try:
        with open("/proc/net/dev") as fh:
            for line in fh:
                if line.strip().startswith(name + ":"):
                    fields = line.split(":")[1].split()
                    return int(fields[0]), int(fields[8])
    except (OSError, IndexError, ValueError):
        pass
    return None


def speeds():
    """(bytes/s in, bytes/s out) since the previous call (0, 0 at first).

    Call it regularly -- the meter calls it every couple of seconds --
    and the numbers are the honest rate of the moment.
    """
    global _last
    now = counters()
    if now is None:
        return 0.0, 0.0
    if _last is None:
        _last = (now[0], now[1], time.monotonic())
        return 0.0, 0.0
    rx, tx, then = _last
    dt = max(0.0, time.monotonic() - then)
    _last = (now[0], now[1], time.monotonic())
    if now[0] < rx or now[1] < tx:
        rx, tx = 0, 0  # a reboot reset the counters mid-sample
    if dt <= 0:
        return 0.0, 0.0
    return (now[0] - rx) / dt, (now[1] - tx) / dt


def _day_file(day=None):
    if day is None:
        day = time.strftime("%Y%m%d")
    return os.path.join(STORAGE, day)


def _read(path):
    try:
        with open(path) as fh:
            rx, tx = fh.read().split()
            return int(rx), int(tx)
    except (OSError, ValueError):
        return 0, 0


def _write(path, rx, tx):
    try:
        os.makedirs(STORAGE, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(f"{rx} {tx}\n")
        os.replace(tmp, path)
    except OSError:
        pass


def record():
    """Add what passed since the previous call to today's file.

    The clock of the meter: called on every poll, it keeps the daily
    figure true while the session runs.  It keeps its own counter, so
    the speeds badge and the daily file never eat each other's ticks.
    """
    global _last_record
    day = time.strftime("%Y%m%d")
    now = counters()
    if _last_record is None or now is None:
        if now is not None:
            _last_record = (now[0], now[1], time.monotonic())
        return
    d_rx = max(0, now[0] - _last_record[0])  # negative = a reboot
    d_tx = max(0, now[1] - _last_record[1])
    _last_record = (now[0], now[1], time.monotonic())
    rx, tx = _read(_day_file(day))
    _write(_day_file(day), rx + d_rx, tx + d_tx)


def day_total(day=None):
    """(received, sent) of one day, in bytes."""
    return _read(_day_file(day))


def week_total():
    """(received, sent) over the last seven days, today in front."""
    rows = sorted(os.listdir(STORAGE)) if os.path.isdir(STORAGE) else []
    rx = tx = 0
    for name in rows[-7:]:
        drx, dtx = day_total(name)
        rx += drx
        tx += dtx
    return rx, tx


def month_total():
    """(received, sent) since the first of the month, in bytes."""
    prefix = time.strftime("%Y%m")
    rows = sorted(os.listdir(STORAGE)) if os.path.isdir(STORAGE) else []
    rx = tx = 0
    for name in rows:
        if name.startswith(prefix):
            drx, dtx = day_total(name)
            rx += drx
            tx += dtx
    return rx, tx


def per_day(days=14):
    """The last days as [(name, rx, tx), ...], today last."""
    rows = sorted(os.listdir(STORAGE)) if os.path.isdir(STORAGE) else []
    out = []
    for name in rows[-days:]:
        drx, dtx = day_total(name)
        out.append((name, drx, dtx))
    return out


def human(n, one_dec=True):
    """Bytes in the form a status row says them."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}" if one_dec else f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
