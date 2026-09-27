#!/usr/bin/env bash
# Installs or updates EWidgets on elementary OS 8:
#
#   wget -qO- https://raw.githubusercontent.com/gornostal/EWidgets/main/install.sh | bash
#
# 1. installs the system packages it needs (asks for your password only if some are missing),
# 2. clones EWidgets into ~/.local/share/ewidgets (or updates it there),
# 3. starts it with your session,
# 4. offers to open it with a three- or four-finger swipe down.
#
# Run it again to update. Set EWIDGETS_DIR to install somewhere else. Run
# from a checkout (bash install.sh), it uses that checkout instead.

# Everything is in functions, called on the last line, so that with
# `wget | bash` the whole script is read before anything runs.

set -euo pipefail

REPO_URL="https://github.com/gornostal/EWidgets.git"
APP_ID="io.github.ewidgets.EWidgets"
PACKAGES=(
    git
    python3-gi               # PyGObject
    python3-gi-cairo         # pycairo, for drawing the blade's shadow
    gir1.2-gtk-4.0           # GTK 4
    libgtk-4-media-gstreamer # lets GTK 4 play the countdown's alarm sound
    gstreamer1.0-plugins-good
)
GESTURES_SCHEMA="io.elementary.desktop.wm.gestures"
TOUCHEGG_CONF="$HOME/.config/touchegg/touchegg.conf"
EWIDGETS_CONF="${XDG_CONFIG_HOME:-$HOME/.config}/ewidgets/ewidgets.conf"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.desktop"

bold=$(tput bold 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

step() { printf '\n%s==> %s%s\n' "$bold" "$*" "$reset"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    %sWarning:%s %s\n' "$bold" "$reset" "$*" >&2; }
die() {
    printf '\n%sError:%s %s\n' "$bold" "$reset" "$*" >&2
    exit 1
}

has_tty() { { : </dev/tty; } 2>/dev/null; }

# ask "question" default -> prints the answer. Reads from the terminal, not
# stdin, which is this script when it's piped into bash.
ask() {
    local reply
    if has_tty; then
        read -r -p "    $1 " reply </dev/tty || reply=""
    else
        reply=""
    fi
    printf '%s' "${reply:-$2}"
}

confirm() {
    local reply
    reply=$(ask "$1 [Y/n]" y)
    [[ $reply =~ ^[Yy] ]]
}

check_system() {
    step "Checking the system"
    if ! grep -qs '^ID=elementary' /etc/os-release; then
        warn "This isn't elementary OS. EWidgets needs elementary OS 8 (Pantheon on Wayland)."
        confirm "Install anyway?" || exit 1
    fi
    command -v apt-get >/dev/null || die "apt-get not found."
    if [[ ${XDG_SESSION_TYPE:-} != wayland ]]; then
        warn "This session isn't Wayland. EWidgets only works in elementary OS's"
        warn "Secure Session: pick it from the gear on the login screen."
    fi
    info "OK"
}

# is_installed package: true if it, or an installed package that provides it,
# is installed. On elementary OS 9, libgtk-4-1 provides libgtk-4-media-gstreamer.
is_installed() {
    dpkg-query -W -f='${db:Status-Abbrev}|${Package}, ${Provides}\n' 2>/dev/null |
        awk -F'|' -v want="$1" '
            $1 ~ /^ii/ {
                n = split($2, names, /, */)
                for (i = 1; i <= n; i++) { split(names[i], name, " "); if (name[1] == want) found = 1 }
            }
            END { exit !found }'
}

install_packages() {
    step "Installing system packages"
    local missing=() package
    for package in "${PACKAGES[@]}"; do
        is_installed "$package" || missing+=("$package")
    done
    if ((${#missing[@]} == 0)); then
        info "Already installed"
        return
    fi
    info "Installing: ${missing[*]}"
    info "(sudo may ask for your password)"
    sudo apt-get update -q </dev/null
    sudo apt-get install -y -q "${missing[@]}" </dev/null

    python3 -c 'import gi; gi.require_version("Gtk", "4.0"); import cairo' 2>/dev/null ||
        die "GTK 4 for Python still doesn't load. Check the apt output above."
}

# Sets $DIR to the EWidgets checkout, cloning or updating it.
get_code() {
    step "Getting EWidgets"
    local here=""
    if [[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]]; then
        here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    fi
    if [[ -z ${EWIDGETS_DIR:-} && -n $here && -f $here/ewidgets/__main__.py ]]; then
        DIR=$here
        info "Using this checkout: $DIR"
        return
    fi

    DIR=${EWIDGETS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/ewidgets}
    if [[ -d $DIR/.git ]]; then
        info "Updating $DIR"
        git -C "$DIR" pull --ff-only -q ||
            warn "Couldn't update (local changes?). Carrying on with the current version."
    elif [[ -e $DIR ]]; then
        die "$DIR exists but isn't a git checkout. Move it away, or set EWIDGETS_DIR."
    else
        info "Cloning into $DIR"
        mkdir -p "$(dirname "$DIR")"
        git clone -q "$REPO_URL" "$DIR"
    fi
}

set_up_autostart() {
    step "Starting EWidgets with your session"
    case $DIR in
        *[\"\`\$\\]*) die "The install path can't contain quotes, backquotes, \$ or backslashes: $DIR" ;;
    esac
    mkdir -p "$(dirname "$AUTOSTART")"
    cat >"$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=EWidgets
Comment=Weather, music, quick toggles and more, a swipe away
Exec="$DIR/bin/ewidgets"
Icon=preferences-desktop-apps
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
    info "Wrote $AUTOSTART"
}

gala_gesture() { gsettings get "$GESTURES_SCHEMA" "$1" 2>/dev/null | tr -d "'"; }

# Frees vertical swipes with $1 fingers in Gala, which binds both swipe up
# and down to whatever $1-finger-swipe-up does. Returns 1 if the user says no.
free_gala_swipe() {
    local fingers=$1 other=$(($1 == 3 ? 4 : 3))
    local key="$(num_word "$fingers")-finger-swipe-up"
    local other_key="$(num_word "$other")-finger-swipe-up"
    local current
    current=$(gala_gesture "$key")
    [[ -z $current || $current == none ]] && return 0

    if [[ $current == multitasking-view ]]; then
        info "A $fingers-finger swipe up opens the Multitasking View, and Gala then"
        info "takes the $fingers-finger swipe down as well."
        confirm "Move the Multitasking View to a $other-finger swipe up?" || return 1
        gsettings set "$GESTURES_SCHEMA" "$other_key" multitasking-view
        info "The Multitasking View now opens with a $other-finger swipe up."
    else
        info "A $fingers-finger swipe up is set to '$current' in Gala, which would also"
        info "take the $fingers-finger swipe down."
        confirm "Turn it off?" || return 1
    fi
    gsettings set "$GESTURES_SCHEMA" "$key" none
}

num_word() { case $1 in 3) echo three ;; 4) echo four ;; esac; }

# EWidgets follows swipes live from the Touchégg daemon, so Touchégg itself
# needs no gesture for it. Earlier instructions had one run bin/ewidgets-toggle
# (since removed), which would toggle the blade on top of the swipe: remove it. Only warns about
# other swipes down with $1 fingers, which Touchégg would run alongside.
clean_up_touchegg() {
    [[ -f $TOUCHEGG_CONF ]] || return 0
    local changed
    changed=$(python3 - "$TOUCHEGG_CONF" "$1" <<'EOF'
import re
import sys
from pathlib import Path

path, fingers = Path(sys.argv[1]), sys.argv[2]
text = path.read_text()


def attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{name}\s*=\s*"([^"]*)"', tag)
    return match and match.group(1)


def drop(match: re.Match) -> str:
    tag, body = match.group("tag"), match.group("body")
    if "ewidgets-toggle" in body:
        return ""
    if (attr(tag, "type"), attr(tag, "fingers"), attr(tag, "direction")) == ("SWIPE", fingers, "DOWN"):
        print(f"    Warning: {path} also does something on a {fingers}-finger swipe down.", file=sys.stderr)
    return match.group(0)


new = re.sub(r"[ \t]*(?P<tag><gesture\b[^>]*>)(?P<body>.*?)</gesture>[ \t]*\n?", drop, text, flags=re.S)
if new != text:
    path.with_name(path.name + ".bak").write_text(text)
    path.write_text(new)
    print("changed")
EOF
    )
    if [[ $changed == changed ]]; then
        info "Removed the old EWidgets gesture from $TOUCHEGG_CONF (backup: $TOUCHEGG_CONF.bak)"
        # Restart the Touchégg client (not the daemon, which runs as root) to reload it.
        pkill -u "$(id -u)" -x touchegg || true
        setsid -f touchegg >/dev/null 2>&1 </dev/null || warn "Couldn't restart Touchégg. Log out and back in."
    fi
}

# Tells the blade how many fingers to follow when it's swiped open or closed.
save_fingers() {
    mkdir -p "$(dirname "$EWIDGETS_CONF")"
    python3 - "$EWIDGETS_CONF" "$1" <<'EOF'
import sys

from gi.repository import GLib

path, fingers = sys.argv[1], int(sys.argv[2])
keyfile = GLib.KeyFile()
try:
    keyfile.load_from_file(path, GLib.KeyFileFlags.KEEP_COMMENTS)
except GLib.Error:
    pass
keyfile.set_integer("gesture", "fingers", fingers)
keyfile.save_to_file(path)
EOF
}

set_up_gesture() {
    step "Setting up the swipe"
    if ! command -v touchegg >/dev/null; then
        warn "Touchégg isn't installed, so there's no swipe. Open EWidgets with:"
        warn "  $DIR/bin/ewidgets toggle"
        return
    fi
    if ! has_tty; then
        info "No terminal to ask in; skipping. Run the installer again from a terminal to set it up."
        return
    fi

    info "EWidgets opens and closes with a swipe down on the touchpad."
    local fingers saved
    saved=$(sed -n 's/^fingers=\s*\([34]\)\s*$/\1/p' "$EWIDGETS_CONF" 2>/dev/null | tail -1 || true)
    saved=${saved:-3}
    while true; do
        fingers=$(ask "How many fingers: 3, 4, or n to skip? [$saved]" "$saved")
        case $fingers in
            3 | 4)
                if gsettings list-keys "$GESTURES_SCHEMA" >/dev/null 2>&1; then
                    free_gala_swipe "$fingers" || continue
                fi
                break
                ;;
            n | N) info "Skipped. You can open EWidgets with $DIR/bin/ewidgets toggle"; return ;;
            *) info "Please answer 3, 4 or n." ;;
        esac
    done

    save_fingers "$fingers"
    clean_up_touchegg "$fingers"
    info "Swipe down with $fingers fingers to open EWidgets, and up (or down again) to close it."
}

start_app() {
    step "Starting EWidgets"
    # Quit a running copy so the new code loads.
    gdbus call --session --dest "$APP_ID" --object-path "/${APP_ID//./\/}" \
        --method org.gtk.Actions.Activate quit '[]' '{}' >/dev/null 2>&1 && sleep 1 || true
    if [[ -z ${WAYLAND_DISPLAY:-} ]]; then
        info "Not in a Wayland session; it'll start next time you log in to the Secure Session."
        return
    fi
    setsid -f "$DIR/bin/ewidgets" show >/dev/null 2>&1 </dev/null
    info "Done. Swipe down (or press Escape, or click elsewhere) to hide it."
}

main() {
    check_system
    install_packages
    get_code
    set_up_autostart
    set_up_gesture
    start_app
    printf '\n%sEWidgets is installed.%s\n' "$bold" "$reset"
}

main "$@"
