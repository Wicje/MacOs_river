#!/bin/sh
# Apply the persisted light/dark palette before the session's UI starts.
# Non-disruptive: only installs CSS/notification files, restarts nothing.
set -eu

CFG="$HOME/.config"
STATE="$CFG/river/.theme"

mode="$(cat "$STATE" 2>/dev/null || printf dark)"
[ "$mode" = "light" ] || mode=dark

if [ -f "$CFG/waybar/style.$mode.css" ]; then
    cp "$CFG/waybar/style.$mode.css" "$CFG/waybar/style.css"
fi
if [ -f "$CFG/wofi/style.$mode.css" ]; then
    cp "$CFG/wofi/style.$mode.css" "$CFG/wofi/style.css"
fi

if [ "$mode" = "dark" ]; then
    printf 'background-color=#0b0b12e6\ntext-color=#ffffff\nborder-color=#ffffff26\n' > "$CFG/mako/theme.conf"
else
    printf 'background-color=#f4f5fbe6\ntext-color=#1b1b21\nborder-color=#0000001f\n' > "$CFG/mako/theme.conf"
fi
