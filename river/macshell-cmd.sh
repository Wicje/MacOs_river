#!/bin/sh
# Send a command to the macshell (menu bar, dock, control centre).
#
# Usage: macshell-cmd.sh cc|spotlight|apple|theme|close|lock|menu:<Title>
set -eu

runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
printf '%s\n' "${1:-}" > "$runtime/macshell.cmd"
