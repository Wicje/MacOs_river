"""The LocalSend protocol, spoken directly.

AirDrop needs AWDL, and this laptop's Broadcom chip cannot do it, so the
nearby transfer rides on LocalSend instead: the phone (or any other
device) runs its little receiver, and we speak its protocol -- a UDP
announcement on 224.0.0.167:53317 for discovery, then a plain HTTPS (or
HTTP) "prepare-upload2" and "upload" pair that the receiver consents to
with one tap.

Everything here is quiet: no threads are spawned, no files are moved --
send() returns (device, ok, reason) and the caller decides what to say.
"""

from __future__ import annotations

import fcntl
import json
import mimetypes
import os
import socket
import ssl
import struct
import time
import urllib.error
import urllib.request

GROUP = "224.0.0.167"
PORT = 53317
ALIAS = "Laptop"
MODEL = "desktop"
FINGERPRINT = "macshell-omega-" + (os.uname().nodename or "omega")

_TIMEOUT = 6.0
_SIOCGIFADDR = 0x8915


def _iface_address(name):
    """The IPv4 address of one interface, or None."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        info = fcntl.ioctl(probe.fileno(), _SIOCGIFADDR,
                           struct.pack("256s", name[:15].encode()))
        return socket.inet_ntoa(info[20:24])
    except OSError:
        return None
    finally:
        probe.close()


def addrs():
    """One address per usable interface; Wi-Fi first, lookback gone."""
    wifi, wired, other = [], [], []
    try:
        with open("/proc/net/dev", encoding="utf8") as fh:
            names = [line.split(":")[0].strip()
                     for line in fh if ":" in line]
    except OSError:
        names = []
    for name in names:
        if name.startswith("lo") or "." in name or ":" in name:
            continue
        try:
            addr = _iface_address(name)
        except OSError:
            continue
        if not addr:
            continue
        (wifi if name.startswith("wl") else wired if
         name.startswith("eth") or name.startswith("enp") or
         name.startswith("usb") else other).append(socket.inet_aton(addr))
    return wifi + wired + other


def _http_request(url, method, headers=None, data=None,
                  tls=False, timeout=_TIMEOUT):
    """One request; returns (status, body bytes, tls)."""
    if tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context))
    else:
        opener = urllib.request.build_opener()
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(), tls
    except urllib.error.HTTPError as error:
        return error.code, error.read(), tls


def discover(timeout=1.8):
    """Whoever is receiving right now: every answer names itself."""
    devices = {}
    deadline = time.monotonic() + timeout
    packs = addrs()
    reader = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                           socket.IPPROTO_UDP)
    reader.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        reader.bind((GROUP, PORT))
    except OSError:
        reader.bind(("", PORT))
    for packed in packs:
        membership = struct.pack("4s4sI", socket.inet_aton(GROUP),
                                 packed, 1)
        try:
            reader.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                              membership)
        except OSError:
            pass
    reader.settimeout(0.35)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                           socket.IPPROTO_UDP)
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    hello = json.dumps({
        "fingerprint": FINGERPRINT,
        "alias": ALIAS,
        "deviceModel": MODEL,
        "type": "announcement",
        "download": True,
    }).encode()
    for packed in packs:
        try:
            sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                              packed)
        except OSError:
            pass
        for target in (GROUP, "255.255.255.255"):
            sender.sendto(hello, (target, PORT))
    while deadline - time.monotonic() > 0:
        try:
            reader.settimeout(min(0.35, deadline - time.monotonic()))
            data, source = reader.recvfrom(8192)
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        if payload.get("fingerprint") == FINGERPRINT:
            continue
        devices[source[0]] = {
            "ip": source[0],
            "port": int(payload.get("port") or 53316),
            "alias": payload.get("alias") or source[0],
            "model": payload.get("deviceModel") or "",
            "fingerprint": payload.get("fingerprint") or "",
        }
        # the answers arrive in a burst: once somebody spoke, wait a
        # little more for the stragglers, but not forever
        deadline = min(deadline, time.monotonic() + 0.6)
    reader.close()
    sender.close()
    return list(devices.values())


def _prepare(device, file_meta, pin=None):
    url = "%s://%s:%d/api/localsend/v2/prepare-upload2" % (
        "https" if device.get("tls") else "http", device["ip"], device["port"])
    payload = {
        "info": {
            "alias": ALIAS,
            "deviceModel": MODEL,
            "fingerprint": FINGERPRINT,
            "port": 0,
            "protocol": 2,
        },
        "files": {"1": dict(file_meta, id="1")},
    }
    headers = {"Content-Type": "application/json"}
    if pin is not None:
        headers["pin"] = str(pin)
    try:
        return _http_request(url, "POST", headers, json.dumps(payload).encode(),
                             tls=device.get("tls", False))
    except OSError:
        return None


def _upload(device, path, session, token):
    url = "%s://%s:%d/api/localsend/v2/upload" % (
        "https" if device.get("tls") else "http", device["ip"], device["port"])
    url += "?sessionId=%s&fileId=1&token=%s" % (session, token)
    with open(path, "rb") as fh:
        payload = fh.read()
    for tls in (device.get("tls"), not device.get("tls")):
        if tls is None:
            continue
        try:
            status, _body, _ = _http_request(
                url, "PUT", {"Content-Type": "application/octet-stream"},
                payload, tls=tls)
            if 200 <= status < 300:
                device["tls"] = tls
                return True
        except OSError:
            continue
    return False


def send(path):
    """Send one file to the best answer in the room.

    Returns (device or None, ok, reason); reason is a short human line.
    """
    if not os.path.exists(path):
        return None, False, "The file is gone from the disk."
    devices = discover()
    if not devices:
        return None, False, ("No nearby LocalSend receivers: open "
                             "LocalSend on the phone and try again.")
    devices.sort(key=lambda d: ("phone" not in d["alias"].lower(),
                                d["alias"].lower()))
    device = devices[0]
    name = os.path.basename(path)
    size = os.path.getsize(path)
    file_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    file_meta = {"fileName": name, "size": size, "fileType": file_type}

    device["tls"] = True
    chosen = None
    for tls in (True, False):
        device["tls"] = tls
        answer = _prepare(device, file_meta)
        if answer is None:
            continue
        status, body = answer[0], answer[1]
        text = (body or b"").decode("utf8", "replace")
        if status == 200:
            try:
                reply = json.loads(text)
            except ValueError:
                continue
            token = (reply.get("files") or {}).get("1", "")
            if not token:
                continue
            ok = _upload(device, path, reply.get("sessionId", ""), token)
            chosen = device
            break
        if status == 401:
            # the receiver wants a PIN and prints it in that answer, so
            # one more round with the pin header goes through
            try:
                pin = json.loads(text).get("pin")
            except ValueError:
                pin = None
            if pin is not None:
                retry = _prepare(device, file_meta, pin=pin)
                if retry and retry[0] == 200:
                    try:
                        reply = json.loads(retry[1].decode())
                        token = (reply.get("files") or {}).get("1", "")
                    except ValueError:
                        token = None
                    if token:
                        ok = _upload(device, path, reply.get("sessionId",
                                                              ""), token)
                        chosen = device
                        break
            return device, False, "%s is asking for the PIN." % device["alias"]
        if status == 403:
            chosen = device
            return chosen, False, ("%s turned the upload off. Allow"
                                   " 'Download' in it." % device["alias"])
    if chosen is None:
        chosen = device
        return chosen, False, ("Nothing answered on %s. Is LocalSend"
                               " open?" % device["alias"])
    return chosen, ok, "Sent" if ok else "The upload failed."
