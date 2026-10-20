"""River IPC client.

River exposes a JSON socket for its controller, which is the only way to
ask it about views, tags and outputs -- the shipped `riverctl` build on
some systems omits the introspection commands.
"""

from __future__ import annotations

import json
import os
import socket

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
SOCKET = os.path.join(RUNTIME, "river-controller.sock")


def _abstract_socket():
    """Find river's controller socket when it is abstract (systemd units)."""
    try:
        with open("/proc/net/unix") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 8:
                    continue
                path = parts[7]
                if path.startswith("@") and "river" in path:
                    return "\0" + path[1:]
    except OSError:
        pass
    return None


def _targets():
    if os.path.exists(SOCKET):
        return [SOCKET]
    abstract = _abstract_socket()
    return [abstract] if abstract else []


def call(*args, timeout=2.0):
    """Send a request to the river controller and return the decoded reply."""
    for target in _targets():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(target)
                sock.sendall(json.dumps(list(args)).encode())
                chunks = []
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
                raw = b"".join(chunks)
        except (OSError, socket.timeout):
            continue
        if not raw:
            continue
        try:
            return json.loads(raw.decode())
        except ValueError:
            continue
    return None


def views():
    """Return the list of views (windows) known to river."""
    reply = call("get-views")
    if isinstance(reply, dict):
        return reply.get("views") or []
    return []


def focused_view():
    reply = call("get-focused-view")
    if isinstance(reply, dict):
        return reply
    return None


def tags():
    reply = call("get-tags")
    if isinstance(reply, dict):
        return reply.get("tags") or []
    return []


def outputs():
    reply = call("get-outputs")
    if isinstance(reply, dict):
        return reply.get("outputs") or []
    return []


def focused_title():
    view = focused_view()
    if not view:
        return ""
    return view.get("title") or ""


def running_apps():
    """Titles of every mapped view, used for the dock's running dots."""
    titles = []
    for view in views():
        if view.get("hidden"):
            continue
        title = view.get("title") or ""
        if title:
            titles.append(title)
    return titles
