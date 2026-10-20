#!/usr/bin/env bash
# Install the macOS shell on this machine, together with the tools and
# applications it likes.
#
#   ./setup.sh              install everything and start the shell
#   ./setup.sh --deps       only install the tools and applications
#   ./setup.sh --check      only report what is missing
#   ./setup.sh --no-deps    install the shell but touch nothing else
#
# The script is safe to run again: everything it does can be undone by
# removing ~/.config/macshell and disabling the two systemd units.

set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
cfg="$HOME/.config"

MODE="all"
case "${1:-}" in
    --deps) MODE="deps" ;;
    --no-deps) MODE="shell" ;;
    --check) MODE="check" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    "") ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
esac

# --- what the shell needs ---------------------------------------------------

# the tools the panels talk to
TOOLS=(playerctl wpctl brightnessctl nmcli bluetoothctl makoctl wl-copy
       wl-paste wtype cliphist grim wayland-scanner gcc python3 python3-gi)

# the applications that belong on the dock
APPS=(ghostty yazi foot mpv vlc dolphin ffmpeg thunar gimp)

# the packages that carry them, per package manager
PACMAN_PKGS=(python python-gobject pycairo gtk3 playerctl wpcli brightnessctl
             networkmanager bluez mako wl-clipboard wtype cliphist grim
             wayland-scanner gcc ghostty yazi foot mpv vlc dolphin dolphin-plugins
             ffmpeg thunar gimp qt5-wayland qt6-wayland
             xdg-desktop-portal-gtk libadwaita
             gvfs-mtp gvfs-gphoto2 gvfs-smb)

APT_PKGS=(python3 python3-gi python3-cairo gir1.2-gtk-3.0 playerctl wpctl
          brightnessctl network-manager bluez mako wl-clipboard wtype
          cliphist grim wayland-scanner build-essential ghostty yazi foot
          mpv vlc dolphin ffmpeg gimp)

DNF_PKGS=(python3 python3-gobject pycairo gtk3 playerctl wpctl brightnessctl
          NetworkManager bluez mako wl-clipboard wtype cliphist grim
          wayland-scanner gcc ghostty yazi foot mpv vlc dolphin ffmpeg gimp)

# the applications that live in the AUR
AUR_PKGS=(spotify steam)

have() { command -v "$1" >/dev/null 2>&1; }

have_pkg() {
    case "$1" in
        pacman) pacman -Q "$2" >/dev/null 2>&1 ;;
        apt) dpkg -s "$2" >/dev/null 2>&1 ;;
        dnf) rpm -q "$2" >/dev/null 2>&1 ;;
    esac
}

pkg_manager() {
    if have pacman; then echo pacman
    elif have apt-get; then echo apt
    elif have dnf; then echo dnf
    else echo none
    fi
}

# --- report -----------------------------------------------------------------

missing_tools() {
    local missing=""
    for tool in "${TOOLS[@]}"; do
        have "$tool" || missing="$missing $tool"
    done
    echo "$missing"
}

missing_apps() {
    local missing=""
    for app in "${APPS[@]}"; do
        have "$app" || missing="$missing $app"
    done
    echo "$missing"
}

report() {
    echo "==> what is already here"
    local tools apps
    tools="$(missing_tools)"
    apps="$(missing_apps)"
    if [ -z "$tools" ]; then
        echo "    every tool the shell needs is installed"
    else
        echo "    missing tools:$tools"
    fi
    if [ -z "$apps" ]; then
        echo "    every application is installed"
    else
        echo "    missing applications:$apps"
    fi
    if have ollama; then
        echo "    ollama is installed (the assistant needs a model: ollama pull llama3.2)"
    else
        echo "    ollama is not installed (the assistant needs it, it is optional)"
    fi
}

if [ "$MODE" = "check" ]; then
    report
    exit 0
fi

# --- the tools and the applications -----------------------------------------

install_deps() {
    local manager pkgs
    manager="$(pkg_manager)"
    if [ "$manager" = "none" ]; then
        echo "==> no supported package manager found; install these yourself:"
        echo "    ${TOOLS[*]}"
        echo "    ${APPS[*]}"
        return 0
    fi

    case "$manager" in
        pacman) pkgs=("${PACMAN_PKGS[@]}") ;;
        apt) pkgs=("${APT_PKGS[@]}") ;;
        dnf) pkgs=("${DNF_PKGS[@]}") ;;
    esac

    echo "==> installing the tools and the applications with $manager"
    if [ "$manager" = "pacman" ]; then
        sudo pacman -S --needed --noconfirm "${pkgs[@]}" || \
            echo "    some packages were refused; install them by hand if needed"
        # the AUR, when a helper is around
        local helper=""
        for candidate in paru yay pikaur; do
            if have "$candidate"; then helper="$candidate"; break; fi
        done
        if [ -n "$helper" ]; then
            for pkg in "${AUR_PKGS[@]}"; do
                echo "    installing $pkg from the AUR with $helper"
                "$helper" -S --needed --noconfirm "$pkg" || \
                    echo "    $pkg was refused"
            done
        else
            echo "    no AUR helper found (paru or yay); Spotify and Steam"
            echo "    can be installed from the AUR by hand"
        fi
    else
        local sudo_cmd=""
        if [ "$(id -u)" != "0" ]; then sudo_cmd="sudo"; fi
        $sudo_cmd apt-get update -y
        $sudo_cmd apt-get install -y "${pkgs[@]}" || \
            echo "    some packages were refused; install them by hand if needed"
    fi
    report
}

if [ "$MODE" = "all" ] || [ "$MODE" = "deps" ]; then
    install_deps
fi

if [ "$MODE" = "deps" ]; then
    exit 0
fi

# --- the shell itself --------------------------------------------------------

echo "==> installing the shell"
if [ "$here" != "$cfg/macshell" ]; then
    mkdir -p "$cfg/macshell"
    cp -r "$here"/. "$cfg/macshell"/
    echo "    copied to $cfg/macshell"
fi
chmod +x "$cfg/macshell/install.sh" 2>/dev/null || true
sh "$cfg/macshell/install.sh"

# the river configuration: keep the one that is already there
if [ -f "$cfg/river/init" ] && ! cmp -s "$cfg/river/init" "$cfg/macshell/river/init"; then
    cp "$cfg/river/init" "$cfg/river/init.macshell.bak"
    cp "$cfg/macshell/river/init" "$cfg/river/init"
    echo "    your river configuration was kept as $cfg/river/init.macshell.bak"
fi

# the dock of the shell: a few more applications to start with
echo "==> checking the dock"
if [ ! -f "$cfg/macshell/dock.json" ]; then
    echo "    the dock starts with the built-in list; change it from the"
    echo "    right click menu of a dock icon"
fi

cat <<'EOF'

==> done

Log out and back in so river picks up the new key bindings, or run the
mappings by hand:

    grep macshell-cmd ~/.config/river/init

The shell is a systemd user service, so it starts with your session:

    systemctl --user status macshell.service
EOF
