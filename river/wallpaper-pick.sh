#!/bin/sh
# Pick a wallpaper from ~/mac and ~/Pictures/wall, or the live aurora.
# Persists the choice in ~/.config/river/.wallpaper and restarts the daemon.
set -eu

dirs="$HOME/mac $HOME/Pictures/wall"
list="Live aurora
"
paths=""
for d in $dirs; do
    [ -d "$d" ] || continue
    for f in "$d"/*.jpeg "$d"/*.jpg "$d"/*.png "$d"/*.webp; do
        [ -f "$f" ] || continue
        list="$list$(basename "$f")
"
        paths="$paths$f
"
    done
done

choice="$(printf '%s' "$list" | wofi --dmenu -i -p 'Wallpaper')" || exit 0
[ -n "$choice" ] || exit 0

state="$HOME/.config/river/.wallpaper"
if [ "$choice" = "Live aurora" ]; then
    rm -f "$state"
else
    path="$(printf '%s' "$paths" | while IFS= read -r p; do
        if [ "$(basename "$p")" = "$choice" ]; then printf '%s' "$p"; break; fi
    done)"
    [ -n "$path" ] || exit 0
    printf '%s\n' "$path" > "$state"
fi

# Restart the wallpaper daemon (exact-argv /proc scan, skips self).
WALL_TARGET=$(printf '%s/%s' "$HOME/.config/river" wallpaper.py) python3 - <<'PY'
import os, signal
target = os.environ["WALL_TARGET"]
me = os.getpid()
for pid in os.listdir('/proc'):
    if not pid.isdigit() or int(pid) == me:
        continue
    try:
        args = open(f'/proc/{pid}/cmdline', 'rb').read().split(b'\0')
    except OSError:
        continue
    if any(a.decode('utf8', 'replace') == target for a in args):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
PY
setsid python3 "$HOME/.config/river/wallpaper.py" > /tmp/river-wall.log 2>&1 &
