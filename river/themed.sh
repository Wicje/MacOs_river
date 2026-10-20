#!/usr/bin/env bash
# River UI - light/dark theme switcher.
# Usage: themed.sh dark|light|toggle
set -euo pipefail

CFG="$HOME/.config"
STATE="$CFG/river/.theme"
mode="${1:-}"

if [[ "$mode" == "toggle" ]]; then
    if [[ "$(cat "$STATE" 2>/dev/null)" == "dark" ]]; then mode=light; else mode=dark; fi
fi
case "$mode" in
    dark|light) ;;
    *) mode=dark ;;
esac
printf '%s\n' "$mode" > "$STATE"

# --- GTK / desktop preference ------------------------------------------------
if command -v gsettings >/dev/null 2>&1; then
    if [[ "$mode" == "dark" ]]; then
        gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' 2>/dev/null || true
        gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita-dark' 2>/dev/null || true
    else
        gsettings set org.gnome.desktop.interface color-scheme 'default' 2>/dev/null || true
        gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita' 2>/dev/null || true
    fi
fi

# --- waybar ------------------------------------------------------------------
if [[ -f "$CFG/waybar/style.$mode.css" ]]; then
    cp "$CFG/waybar/style.$mode.css" "$CFG/waybar/style.css"
fi
if command -v pgrep >/dev/null 2>&1; then
    pid="$(pgrep -x waybar | head -1 || true)"
    [[ -n "${pid:-}" ]] && kill -SIGUSR2 "$pid" 2>/dev/null || true
fi

# --- wofi --------------------------------------------------------------------
if [[ -f "$CFG/wofi/style.$mode.css" ]]; then
    cp "$CFG/wofi/style.$mode.css" "$CFG/wofi/style.css"
fi

# --- mako --------------------------------------------------------------------
mako_conf="$CFG/mako/theme.conf"
if [[ "$mode" == "dark" ]]; then
    printf 'background-color=#0b0b12e6\ntext-color=#ffffff\nborder-color=#ffffff26\n' > "$mako_conf"
else
    printf 'background-color=#f4f5fbe6\ntext-color=#1b1b21\nborder-color=#0000001f\n' > "$mako_conf"
fi
command -v makoctl >/dev/null 2>&1 && makoctl reload 2>/dev/null || true

# --- close open popups so they reload with the new palette --------------------
for f in /tmp/river-cc-*.pid /tmp/river-np-*.pid /tmp/river-cal-*.pid \
         /tmp/river-power-*.pid /tmp/river-shot-*.pid; do
    [[ -f "$f" ]] && kill "$(cat "$f")" 2>/dev/null || true
done

# --- the macOS shell picks the palette up from its own config --------------
"$CFG/macshell/theme-apply.sh" 2>/dev/null || true

command -v notify-send >/dev/null 2>&1 && \
    notify-send -a "Appearance" "Switched to ${mode} mode" 2>/dev/null || true
