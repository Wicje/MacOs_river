#!/bin/sh
# Install the macOS shell on this machine.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
cfg="$HOME/.config"

echo "==> copying the river integration files"
mkdir -p "$cfg/river"
for file in init wallpaper.py macshell-cmd.sh nightlight.py \
            theme-apply.sh themed.sh wallpaper-pick.sh; do
    if [ -f "$here/river/$file" ]; then
        cp "$here/river/$file" "$cfg/river/$file"
        chmod +x "$cfg/river/$file" || true
    fi
done

echo "==> installing the dock icons"
mkdir -p "$HOME/.local/share/macshell/icons"
cp "$here"/icons/*.png "$HOME/.local/share/macshell/icons/" 2>/dev/null || true

echo "==> building the toplevel helper"
if command -v wayland-scanner >/dev/null 2>&1 && command -v gcc >/dev/null 2>&1; then
    "$here/tools/toplevels/build.sh"
else
    echo "    skipped (wayland-scanner and gcc are needed)"
fi

echo "==> installing the systemd units"
mkdir -p "$cfg/systemd/user"
cp "$here/systemd/macshell.service" "$cfg/systemd/user/"
cp "$here/systemd/macshell-wallpaper.service" "$cfg/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now macshell.service
systemctl --user enable --now macshell-wallpaper.service

echo
echo "Done.  Log out and back in so river picks up the new key bindings,"
echo "or run the mappings by hand:"
echo "  grep macshell-cmd $cfg/river/init"
