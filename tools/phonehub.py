"""Phone hub — the laptop side of Continuity.

A small web service the phone opens over the local network:
the clipboard goes both ways, links arrive as notifications and files
land on the laptop without a cable.  Nothing is trustworthy by itself:
every request has to carry the pairing token, which the laptop shows
once when it starts, and the clipboard is only moved when somebody asks
for it — nothing is sent on its own.

    python3 tools/phonehub.py [--port 8791]

The service is stdlib only, one file, nobody's dependency."""

from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import socket
import subprocess
import sys
import urllib.parse

STATE_DIR = os.path.expanduser("~/.local/state/macshell")
PAIR_FILE = os.path.join(STATE_DIR, "phonehub.json")
INBOX = os.path.expanduser("~/Downloads/phone")
MAX_BODY = 512 * 1024 * 1024

_PAIR = None


def pair():
    """The pairing token, made once and kept."""
    global _PAIR
    if _PAIR is not None:
        return _PAIR
    try:
        with open(PAIR_FILE) as fh:
            _PAIR = dict(json.load(fh))
    except (OSError, ValueError):
        _PAIR = None
    if not _PAIR:
        _PAIR = {"token": secrets.token_hex(12)}
        os.makedirs(os.path.dirname(PAIR_FILE), exist_ok=True)
        with open(PAIR_FILE, "w") as fh:
            json.dump(_PAIR, fh, indent=2)
        os.chmod(PAIR_FILE, 0o600)
    return _PAIR


def lan_address():
    """The address the phone should open."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def wl_copy(text):
    subprocess.run(["wl-copy"], input=text.encode(),
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=5)


def wl_paste():
    out = subprocess.run(["wl-paste", "--no-newline"],
                         capture_output=True, timeout=5)
    return out.stdout.decode("utf-8", "replace")[:200000]


def notify(title, body):
    subprocess.Popen(["notify-send", "-a", "Phone Hub", title, body,
                      "-t", "5000"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "phonehub/1"
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt, *args):  # quiet, phone sites ping a lot
        pass

    def token(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        values = query.get("t")
        if values:
            return values[0]
        return self.headers.get("X-Phonehub-Token", "")

    def ok(self, body, kind="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def deny(self):
        # every stop-gap answer carries a real Content-Length: under
        # HTTP/1.1 the peer otherwise waits for the body forever
        data = b"wrong token"
        self.send_response(403)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return b""
        return self.rfile.read(length)

    def route(self, post=False):
        if self.token() != pair()["token"]:
            self.deny()
            return None
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, (post or self.command == "POST")

    # -- requests ---------------------------------------------------------

    def do_GET(self):
        where = self.route()
        if not where:
            return
        path = where[0]
        if path == "/" or path == "/p" or path == "/index.html":
            self.ok(PAGE, "text/html; charset=utf-8")
        elif path == "/clip":
            self.ok(json.dumps({"text": wl_paste()}))
        elif path == "/ping":
            self.ok(json.dumps({"host": socket.gethostname()}))
        else:
            data = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        where = self.route(post=True)
        if not where:
            return
        path = where[0]
        if path == "/clip":
            data = json.loads(self.body().decode("utf-8") or "{}")
            text = data.get("text") or ""
            if not text:
                self.deny()
                return
            wl_copy(text)
            notify("Phone → Laptop",
                   (text[:120] + ("…" if len(text) > 120 else "")))
            self.ok(json.dumps({"done": True}))
        elif path == "/link":
            data = json.loads(self.body().decode("utf-8") or "{}")
            link = data.get("url") or ""
            if link:
                notify("Phone → Laptop(link)", link)
                self.ok(json.dumps({"done": True}))
            else:
                self.deny()
        elif path == "/file":
            self.receive_file()
        else:
            data = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def receive_file(self):
        os.makedirs(INBOX, exist_ok=True)
        ctype = self.headers.get("Content-Type", "")
        # the page sends the name with encodeURIComponent, so the header
        # stays latin1 safe for every filename
        name = urllib.parse.unquote(
            self.headers.get("X-Phonehub-Name", "file.bin"))
        name = os.path.basename(name) or "file.bin"
        path = os.path.join(INBOX, name)
        if os.path.lexists(path):
            # nothing is overwritten quietly: the second copy becomes copy (1)
            base, ext = os.path.splitext(path)
            index = 1
            while os.path.lexists(f"{base} ({index}){ext}"):
                index += 1
            path = f"{base} ({index}){ext}"
        # the phone sends the raw bytes: nothing to parse, padding only
        count = 0
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_response(413)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        with open(path, "wb") as fh:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(131072, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                remaining -= len(chunk)
                count += len(chunk)
        notify("Phone → Laptop(file)", f"{name} in the laptop's phone inbox")
        self.ok(json.dumps({"done": True, "bytes": count, "path": path}))


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phone hub</title>
<style>
 body{font-family:-apple-system,sans-serif;background:#101014;color:#eee;
      margin:0;padding:20px;max-width:640px}
 h2{margin:24px 0 8px;font-size:1em;color:#9aa2b1}
 textarea,input{width:100%;box-sizing:border-box;padding:10px;border-radius:10px;
      border:1px solid #33363d;background:#17181d;color:#eee;font-size:1em}
 button{margin-top:8px;padding:10px 16px;border-radius:10px;border:0;
      background:#2f6bff;color:#fff;font-size:1em}
 button.ghost{background:#272a31}
 .ok{color:#6fe06a;font-size:.9em}
 .row{display:flex;gap:8px}
</style></head><body>
<h1>Phone hub</h1>
<p class=ok id=out></p>
<h2>Copy to the laptop</h2>
<textarea id=send rows=4 placeholder="text for the laptop clipboard, a link…"></textarea>
<button onclick="postText()">Send to laptop</button>
<h2>The laptop clipboard now</h2>
<textarea id=clip rows=4 readonly></textarea>
<div class=row>
  <button onclick=pull()>Refresh</button>
  <button class=ghost onclick=copyshown()>Copy above</button>
</div>
<h2>Send a file to the laptop</h2>
<input type=file id=file multiple>
<button onclick=upload()>Upload</button>
<hr style=opacity:.3;margin:32px 0>
<small>the pairing token is kept in this browser; hover the address bar to
check you are on the laptop's own network</small>
<script>
const TOKEN = new URLSearchParams(location.search).get('t') || '';
// the browser only exposes navigator.clipboard on https, and the hub
// runs on plain http of the local network: copy() therefore falls back
// to the old execCommand, which still works inside a click gesture
function copy(text, direct){
  // the browser only exposes navigator.clipboard on https, and the hub
  // runs on plain http of the local network: the fallback uses the old
  // execCommand, which still works inside a click gesture
  if (navigator.clipboard && navigator.clipboard.writeText && !direct)
    navigator.clipboard.writeText(text).catch(() => { copy(text, true); });
  else try {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(area);
    area.select();
    const done = document.execCommand('copy');
    document.body.removeChild(area);
    if (!done && !direct) copy(text, true);
  } catch (e) {}
  document.getElementById('out').textContent = 'copied ✓';
}
fetch('/ping?t=' + TOKEN).then(r => r.ok ? r.json() : null)
  .then(j => { document.getElementById('out').textContent =
      j ? 'paired with ' + j.host : 'wrong token'; });
function postText(){
  const t = document.getElementById('send').value;
  const isLink = /^https?:\\/\\//i.test(t.trim());
  fetch((isLink ? '/link' : '/clip') + '?t=' + TOKEN,
    {method:'POST',headers:{'Content-Type':'application/json',
     'X-Phonehub-Token':TOKEN},body:JSON.stringify(isLink?{url:t}:{text:t})})
    .then(r => r.ok ? document.getElementById('send').value = '' : null);
}
async function pull(){
  const j = await (await fetch('/clip?t=' + TOKEN,
    {headers:{'X-Phonehub-Token':TOKEN}})).json();
  document.getElementById('clip').value = j.text || '';
  document.getElementById('out').textContent =
      j.text ? j.text.length + ' characters on the laptop' : 'empty';
}
function copyshown(){
  // the fetch may take too long for Safari, so the write happens
  // directly in the click, on what is already shown
  copy(document.getElementById('clip').value);
}
function upload(){
  const files = document.getElementById('file').files;
  for (const f of files){
    fetch('/file?t=' + TOKEN,{method:'POST',
      headers:{'X-Phonehub-Token':TOKEN,
               'X-Phonehub-Name':encodeURIComponent(f.name)},body:f});
  }
  document.getElementById('out').textContent = 'sending…';
}
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    token = pair()["token"]
    ip = lan_address()
    print(f"phone hub: open http://{ip}:{args.port}/?t={token} on the phone",
          flush=True)
    notify("Phone hub ready", f"http://{ip}:{args.port}/?t={token[:4]}…\n"
           "open it on the phone (the whole address was printed in the journal)")
    http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
