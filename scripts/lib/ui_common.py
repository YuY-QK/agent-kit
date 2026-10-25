"""Shared pieces for agent-kit's local web pages (conflict review and settings form).

Only the Python standard library is used (compatible with the python3 3.9 that ships
with macOS). Pages run on 127.0.0.1 only, require a one-time token, and shut down after
the user submits, cancels, or after a timeout.
"""

import json
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TIMEOUT_SECONDS = 30 * 60
MAX_BODY = 8 * 1024 * 1024

_LINE = re.compile(r"^([MW])_([A-Za-z0-9_]+)='(.*)'\s*$")


def load_messages(kit_dir, lang):
    """Read M_ and W_ keys from scripts/i18n/en.sh, overlaid with the given language."""
    out = {}
    for code in ("en", lang):
        path = os.path.join(kit_dir, "scripts", "i18n", code + ".sh")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = _LINE.match(line)
                if m:
                    out[m.group(2)] = m.group(3)
    return out


def read_kv(path):
    """Read KEY="value" lines from a shell settings file (no execution)."""
    out = {}
    if not os.path.isfile(path):
        return out
    home = os.path.expanduser("~")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if not re.match(r"^[A-Z0-9_]+$", k):
                continue
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k] = v.replace("$HOME", home)
    return out


def pretty(path, home):
    if path and (path == home or path.startswith(home + os.sep)):
        return "~" + path[len(home):]
    return path


BASE_CSS = r"""
:root {
  --bg: #f6f5f2; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6a66; --faint: #9a9892; --line: #e3e1db;
  --accent: #2f5bd3; --accent-soft: #e8eefc; --accent-ink: #ffffff;
  --warn: #b4540b; --warn-bg: #fdf1e5; --ok: #1f7a44; --ok-bg: #e5f4ea;
  --left: #c2410c; --left-bg: #fdeee6; --left-mark: #f8c9b1;
  --right: #15803d; --right-bg: #e7f5ec; --right-mark: #b5e2c4;
  --code-bg: #faf9f7; --marker-bg: #fff4cc;
  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #a19f99; --faint: #74726d; --line: #34332f;
    --accent: #7c9cf5; --accent-soft: #232b42; --accent-ink: #10131c;
    --warn: #f0a35c; --warn-bg: #3a2a1b; --ok: #6fcf97; --ok-bg: #1b3024;
    --left: #f59e6b; --left-bg: #3a241a; --left-mark: #6b3a22;
    --right: #6fcf97; --right-bg: #1a3324; --right-mark: #2c5a3c;
    --code-bg: #191918; --marker-bg: #3d3519; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #a19f99; --faint: #74726d; --line: #34332f;
  --accent: #7c9cf5; --accent-soft: #232b42; --accent-ink: #10131c;
  --warn: #f0a35c; --warn-bg: #3a2a1b; --ok: #6fcf97; --ok-bg: #1b3024;
  --left: #f59e6b; --left-bg: #3a241a; --left-mark: #6b3a22;
  --right: #6fcf97; --right-bg: #1a3324; --right-mark: #2c5a3c;
  --code-bg: #191918; --marker-bg: #3d3519; --shadow: none;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  padding-bottom: 110px;
}
main { max-width: 1240px; margin: 0 auto; padding: 32px 20px; }
h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -.01em; }
h2 { font-size: 17px; margin: 0; }
.lead { color: var(--muted); margin: 0 0 18px; max-width: 840px; }
.mono, .path { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.topbar { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); margin-bottom: 20px; overflow: hidden; }
.sec-head { padding: 16px 20px; border-bottom: 1px solid var(--line); }
.sec-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.btn { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 8px; padding: 8px 16px; font: inherit; font-size: 14px; cursor: pointer; }
.btn.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
button:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 5; background: var(--panel); border-top: 1px solid var(--line); }
.foot { max-width: 1240px; margin: 0 auto; padding: 12px 20px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.foot .sum { flex: 1; min-width: 220px; font-size: 14px; }
.foot .sum small { display: block; color: var(--muted); font-size: 12.5px; }
.error { color: var(--warn); font-size: 13px; width: 100%; }
.finished { max-width: 560px; margin: 18vh auto; text-align: center; padding: 0 20px; }
.finished h1 { color: var(--ok); }
textarea, input[type=text], select { font: inherit; color: var(--ink); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
"""


def page_shell(lang, title, css, body_data, script):
    data = json.dumps(body_data, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<!doctype html>\n<html lang="%s">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n<style>%s%s</style>\n</head>\n<body>\n"
        '<main id="app"></main>\n<footer id="footer"></footer>\n'
        '<script id="data" type="application/json">%s</script>\n<script>%s</script>\n</body>\n</html>\n'
    ) % (lang, title, BASE_CSS, css, data, script)


# Shared JavaScript helpers: esc(), T(key, ...args), post(), theme toggle, finish().
BASE_JS = r"""
var DATA = JSON.parse(document.getElementById("data").textContent);
var MSG = DATA.messages || {};
var TOKEN = DATA.token;
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
// T(key, args...): message with %s placeholders filled in order, HTML-escaped.
function T(key) {
  var s = MSG[key] != null ? MSG[key] : key, args = Array.prototype.slice.call(arguments, 1), k = 0;
  s = s.replace(/%%/g, "\u0000").replace(/%s/g, function () { return args[k++] == null ? "" : String(args[k - 1]); }).replace(/\u0000/g, "%");
  return esc(s);
}
// TH(key, args...): same as T, but the message itself may contain simple HTML (<b>); args are escaped.
function TH(key) {
  var s = MSG[key] != null ? MSG[key] : key, args = Array.prototype.slice.call(arguments, 1), k = 0;
  return s.replace(/%s/g, function () { return esc(args[k++]); });
}
function post(path, body) {
  return fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: JSON.stringify(body || {})
  }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
}
function toggleTheme() {
  var root = document.documentElement;
  var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
}
function finish(title, text) {
  document.getElementById("footer").innerHTML = "";
  document.getElementById("app").innerHTML = '<div class="finished"><h1>' + title + "</h1><p>" + text + "</p></div>";
}
"""


class App(object):
    """Subclass and implement page(), and handle(path, payload) -> (ok, body_dict, finished)."""

    def __init__(self):
        self.token = secrets.token_urlsafe(18)
        self.done = threading.Event()
        self.result = 1

    def page(self):
        raise NotImplementedError

    def handle(self, path, payload):
        raise NotImplementedError


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def send(self, code, body, ctype="text/html; charset=utf-8"):
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(raw)

        def send_json(self, code, obj):
            self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            token = parse_qs(url.query).get("t", [""])[0]
            if not self.host_ok() or token != app.token:
                self.send(403, "forbidden", "text/plain; charset=utf-8")
                return
            if url.path == "/":
                self.send(200, app.page())
            else:
                self.send(404, "not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self.host_ok() or self.headers.get("X-Token") != app.token:
                self.send_json(403, {"error": "forbidden"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self.send_json(413, {"error": "too large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                self.send_json(400, {"error": "bad request"})
                return
            path = urlparse(self.path).path
            if path == "/cancel":
                app.result = 1
                self.send_json(200, {"ok": True})
                app.done.set()
                return
            try:
                ok, body, finished = app.handle(path, payload)
            except Exception as exc:  # report instead of hanging the page
                ok, body, finished = False, {"error": str(exc)}, False
            self.send_json(200 if ok else 400, body)
            if ok and finished:
                app.result = 0
                app.done.set()

    return Handler


def serve(app, messages, no_open=False, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(app))
    url = "http://127.0.0.1:%d/?t=%s" % (server.server_address[1], app.token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(messages.get("term_url", "Page address:") + " " + url)
    print(messages.get("term_hint", "If the browser did not open, paste the address above into it. Press Ctrl+C to cancel."))
    sys.stdout.flush()
    if not no_open and os.environ.get("AGENT_KIT_NO_BROWSER") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        finished = app.done.wait(TIMEOUT_SECONDS)
    except KeyboardInterrupt:
        finished = False
        app.result = 1
    time.sleep(0.3)
    server.shutdown()
    if not finished:
        print(messages.get("term_timeout", "Timed out or cancelled."))
        return 1
    return app.result
