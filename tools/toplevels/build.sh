#!/bin/sh
# Rebuild the toplevel helper used by the shell.
#
# River Classic has no introspection command, so the shell reads the list of
# windows through the wlr-foreign-toplevel protocol.  The helper is a small
# C program; this script regenerates it from the protocol description.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
out="$HOME/.local/bin/macshell-toplevels"

xml="$here/wlr-foreign-toplevel-management-unstable-v1.xml"
header="$here/wlr-toplevel-client-protocol.h"
code="$here/wlr-toplevel-protocol.c"

if [ ! -f "$header" ] || [ "$xml" -nt "$header" ]; then
    wayland-scanner client-header "$xml" "$header"
fi
if [ ! -f "$code" ] || [ "$xml" -nt "$code" ]; then
    wayland-scanner private-code "$xml" "$code"
fi

mkdir -p "$(dirname "$out")"
gcc -O2 -o "$out" "$here/macshell-toplevels.c" "$code" -I"$here" -lwayland-client
echo "built $out"
