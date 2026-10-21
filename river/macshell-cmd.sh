#!/bin/sh
# Send a command to the macshell (menu bar, dock, control centre).
#
# Usage: macshell-cmd.sh cc|spotlight|apple|theme|close|lock|menu:<Title>
#        macshell-cmd.sh tag 3
set -eu

runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
# every argument is sent, so "tag 3" arrives as "tag 3"
printf '%s\n' "$*" > "$runtime/macshell.cmd"
