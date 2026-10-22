#!/usr/bin/env python3
"""agent-kit 安装冲突处理网页。

由 scripts/install.sh 调用，不需要单独运行。只用 Python 标准库（兼容 macOS 自带的 python3 3.9）。

流程：读取安装计划（plan.tsv）→ 在本机 127.0.0.1 上启动临时网页 → 用户在浏览器里
查看差异、选择处理方式、可选地合并编辑 → 点“应用”后写出决定（decisions.tsv）并退出。
合并编辑的内容直接写回 agent-kit 仓库里对应的文件。

退出码：0 = 已应用；1 = 取消或超时。
"""

import argparse
import difflib
import html
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_READ = 512 * 1024
MAX_WRITE = 1024 * 1024
TIMEOUT_SECONDS = 30 * 60

FIELDS = ["id", "kind", "tool", "name", "src", "dest", "status"]
STATUS_LABEL = {
    "new": "新增",
    "update": "更新",
    "uptodate": "已是最新",
    "conflict": "冲突",
    "foreign": "其他来源",
}


def read_text(path):
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_READ + 1)
    except OSError:
        return None
    text = data[:MAX_READ].decode("utf-8", errors="replace")
    if len(data) > MAX_READ:
        text += "\n…（文件太大，只显示前 512 KB）"
    return text


def main_file(path):
    """技能是目录时，比较其中的 SKILL.md；规则是单个文件。"""
    if os.path.isdir(path):
        return os.path.join(path, "SKILL.md")
    return path


def list_files(root):
    out = set()
    if not os.path.isdir(root):
        return out
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith(".") and name != ".agent-kit":
                continue
            if name == ".agent-kit":
                continue
            out.add(os.path.relpath(os.path.join(base, name), root))
    return out


def description_of(text):
    if not text or not text.startswith("---"):
        return ""
    for line in text.splitlines()[1:40]:
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            return line[len("description:"):].strip().strip('"').strip("'")
    return ""


def file_info(path):
    try:
        st = os.stat(path)
    except OSError:
        return ""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
    if os.path.isdir(path):
        return "文件夹 · 修改于 " + stamp
    size = st.st_size
    size_text = "%d B" % size if size < 1024 else "%.1f KB" % (size / 1024.0)
    return "%s · 修改于 %s" % (size_text, stamp)


class Review(object):
    def __init__(self, plan_path, decisions_path, kit_dir, home):
        self.plan_path = plan_path
        self.decisions_path = decisions_path
        self.kit_dir = os.path.realpath(kit_dir)
        self.home = home
        self.token = secrets.token_urlsafe(18)
        self.done = threading.Event()
        self.result = 1
        self.items = self.load_plan()

    def pretty(self, path):
        if path and (path == self.home or path.startswith(self.home + os.sep)):
            return "~" + path[len(self.home):]
        return path

    def load_plan(self):
        items = []
        with open(self.plan_path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != len(FIELDS):
                    continue
                item = dict(zip(FIELDS, parts))
                items.append(item)
        for item in items:
            self.enrich(item)
        return items

    def enrich(self, item):
        item["dest_pretty"] = self.pretty(item["dest"])
        item["status_label"] = STATUS_LABEL.get(item["status"], item["status"])
        item["dest_info"] = file_info(item["dest"])
        if item["status"] == "foreign":
            item["description"] = description_of(read_text(main_file(item["dest"])) or "")
            return
        if item["status"] != "conflict":
            return
        old_path = main_file(item["dest"])
        new_path = main_file(item["src"])
        old = read_text(old_path)
        new = read_text(new_path) or ""
        item["kit_file"] = self.pretty(new_path)
        item["old_text"] = old if old is not None else ""
        item["new_text"] = new
        item["old_readable"] = old is not None
        item["description"] = description_of(new)
        if old is None:
            item["diff_html"] = '<p class="muted">原来的内容不是可读的文本文件（可能是失效的链接），无法显示差异。</p>'
        else:
            table = difflib.HtmlDiff(tabsize=2).make_table(
                old.splitlines(), new.splitlines(), "你原来的", "agent-kit", context=True, numlines=3
            )
            item["diff_html"] = table
        notes = []
        if os.path.isdir(item["dest"]) and os.path.isdir(item["src"]):
            a = list_files(item["dest"])
            b = list_files(item["src"])
            only_old = sorted(a - b)
            only_new = sorted(b - a)
            if only_old:
                notes.append("只在你原来的里有：" + "、".join(only_old))
            if only_new:
                notes.append("只在 agent-kit 里有：" + "、".join(only_new))
        item["notes"] = notes

    # ---- 提交 ----
    def apply(self, payload):
        decisions = payload.get("decisions") or {}
        merges = payload.get("merges") or {}
        by_id = dict((i["id"], i) for i in self.items)
        allowed = {"conflict": ("keep", "replace", "merge"), "foreign": ("keep", "disable")}
        lines = []
        merge_targets = {}
        for item_id, action in decisions.items():
            item = by_id.get(str(item_id))
            if not item or item["status"] not in allowed:
                return "无效的项目编号：%s" % item_id
            if action not in allowed[item["status"]]:
                return "无效的处理方式：%s" % action
            if action == "merge":
                content = merges.get(str(item_id))
                if not isinstance(content, str) or not content.strip():
                    return "“%s”选择了合并编辑，但合并后的内容为空。" % item["name"]
                if len(content.encode("utf-8")) > MAX_WRITE:
                    return "“%s”合并后的内容太大。" % item["name"]
                target = os.path.realpath(main_file(item["src"]))
                if not target.startswith(self.kit_dir + os.sep):
                    return "合并目标不在 agent-kit 仓库内，已拒绝。"
                previous = merge_targets.get(target)
                if previous is not None and previous != content:
                    return "“%s”在两个工具里共用同一份 agent-kit 文件，但两处合并内容不一样，请保持一致。" % item["name"]
                merge_targets[target] = content
                action = "replace"
            lines.append("%s\t%s\n" % (item_id, action))
        for target, content in merge_targets.items():
            if not content.endswith("\n"):
                content += "\n"
            tmp = target + ".tmp-agent-kit"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, target)
        with open(self.decisions_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return None

    def page(self):
        public = []
        for i in self.items:
            keep = dict(i)
            keep.pop("src", None)
            keep.pop("dest", None)
            public.append(keep)
        data = json.dumps({"items": public, "token": self.token}, ensure_ascii=False)
        data = data.replace("</", "<\\/")
        return PAGE.replace("__DATA__", data)


def make_handler(review):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def token_ok(self):
            q = parse_qs(urlparse(self.path).query)
            return q.get("t", [""])[0] == review.token or self.headers.get("X-Token") == review.token

        def send(self, code, body, ctype="text/html; charset=utf-8"):
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if urlparse(self.path).path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if not self.host_ok() or not self.token_ok():
                self.send(403, "forbidden", "text/plain; charset=utf-8")
                return
            if urlparse(self.path).path == "/":
                self.send(200, review.page())
            else:
                self.send(404, "not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self.host_ok() or self.headers.get("X-Token") != review.token:
                self.send(403, json.dumps({"error": "forbidden"}), "application/json")
                return
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            if length > 8 * MAX_WRITE:
                self.send(413, json.dumps({"error": "提交内容太大"}), "application/json")
                return
            body = self.rfile.read(length) if length else b"{}"
            if path == "/cancel":
                review.result = 1
                self.send(200, json.dumps({"ok": True}), "application/json")
                review.done.set()
                return
            if path != "/apply":
                self.send(404, json.dumps({"error": "not found"}), "application/json")
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError:
                self.send(400, json.dumps({"error": "提交格式不正确"}), "application/json")
                return
            error = review.apply(payload)
            if error:
                self.send(400, json.dumps({"error": error}, ensure_ascii=False), "application/json; charset=utf-8")
                return
            review.result = 0
            self.send(200, json.dumps({"ok": True}), "application/json")
            review.done.set()

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--kit", required=True)
    parser.add_argument("--home", default=os.path.expanduser("~"))
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    review = Review(args.plan, args.decisions, args.kit, args.home)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(review))
    port = server.server_address[1]
    url = "http://127.0.0.1:%d/?t=%s" % (port, review.token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("网页地址：" + url)
    print("如果浏览器没有自动打开，请复制上面的地址到浏览器。按 Ctrl+C 取消。")
    sys.stdout.flush()
    if not args.no_open and os.environ.get("AGENT_KIT_NO_BROWSER") != "1":
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        finished = review.done.wait(TIMEOUT_SECONDS)
    except KeyboardInterrupt:
        finished = False
        review.result = 1
    time.sleep(0.3)
    server.shutdown()
    if not finished:
        print("超时或已取消。")
        return 1
    return review.result


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>agent-kit 冲突处理</title>
<style>
:root {
  --bg: #f6f5f2; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6a66; --line: #e3e1db;
  --accent: #2f5bd3; --accent-ink: #ffffff; --warn: #b4540b; --warn-bg: #fdf1e5;
  --add-bg: #e3f4e6; --sub-bg: #fbe3e1; --chg-bg: #fff3c4; --code-bg: #faf9f7;
  --ok: #1f7a44; --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #a19f99; --line: #34332f;
    --accent: #7c9cf5; --accent-ink: #10131c; --warn: #f0a35c; --warn-bg: #3a2a1b;
    --add-bg: #1f3a27; --sub-bg: #43231f; --chg-bg: #3d3519; --code-bg: #191918;
    --ok: #6fcf97; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #a19f99; --line: #34332f;
  --accent: #7c9cf5; --accent-ink: #10131c; --warn: #f0a35c; --warn-bg: #3a2a1b;
  --add-bg: #1f3a27; --sub-bg: #43231f; --chg-bg: #3d3519; --code-bg: #191918;
  --ok: #6fcf97; --shadow: none;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  padding-bottom: 96px;
}
main { max-width: 1180px; margin: 0 auto; padding: 32px 20px; }
h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -.01em; }
h2 { font-size: 17px; margin: 0; }
.lead { color: var(--muted); margin: 0 0 20px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; }
.chip { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 3px 12px; font-size: 13px; color: var(--muted); }
.chip b { color: var(--ink); font-weight: 600; margin-left: 4px; }
.chip.hot { border-color: var(--warn); color: var(--warn); background: var(--warn-bg); }
.chip.hot b { color: var(--warn); }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); margin-bottom: 20px; overflow: hidden; }
.sec-head { padding: 16px 20px; border-bottom: 1px solid var(--line); }
.sec-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.table-wrap { overflow-x: auto; }
table.list { width: 100%; border-collapse: collapse; }
table.list th, table.list td { text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--line); vertical-align: top; }
table.list th { font-size: 12px; color: var(--muted); font-weight: 500; background: var(--code-bg); white-space: nowrap; }
table.list tr:last-child td { border-bottom: none; }
.name { font-weight: 600; }
.path { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; color: var(--muted); word-break: break-all; }
.meta { font-size: 12px; color: var(--muted); }
.desc { font-size: 13px; color: var(--muted); max-width: 420px; }
.tag { display: inline-block; font-size: 12px; border-radius: 6px; padding: 1px 8px; background: var(--code-bg); border: 1px solid var(--line); color: var(--muted); }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.seg button { border: 0; background: transparent; color: var(--ink); padding: 6px 12px; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
.seg button + button { border-left: 1px solid var(--line); }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); }
.seg button:focus-visible, .btn:focus-visible, .link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.link { border: 0; background: none; color: var(--accent); cursor: pointer; font: inherit; font-size: 13px; padding: 0; margin-top: 8px; }
tr.detail td { background: var(--code-bg); padding: 16px; }
.notes { margin: 0 0 10px; padding-left: 18px; font-size: 13px; color: var(--muted); }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--muted); margin-bottom: 8px; flex-wrap: wrap; }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.legend .l-add::before { background: var(--add-bg); } .legend .l-sub::before { background: var(--sub-bg); } .legend .l-chg::before { background: var(--chg-bg); }
.diffbox { overflow: auto; max-height: 460px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
table.diff { border-collapse: collapse; width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
table.diff td, table.diff th { padding: 1px 8px; vertical-align: top; }
table.diff td { white-space: pre-wrap; word-break: break-all; }
table.diff th.diff_header { background: var(--code-bg); color: var(--muted); font-weight: 500; text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
table.diff td.diff_header { color: var(--muted); text-align: right; user-select: none; width: 1%; white-space: nowrap; word-break: normal; }
table.diff td.diff_next, table.diff th.diff_next { display: none; }
table.diff colgroup { display: none; }
.diff_add { background: var(--add-bg); } .diff_sub { background: var(--sub-bg); } .diff_chg { background: var(--chg-bg); }
table.diff td:nth-child(3) { border-right: 1px solid var(--line); }
.merge { margin-top: 16px; }
.merge h3 { font-size: 14px; margin: 0 0 4px; }
.merge p { margin: 0 0 10px; font-size: 13px; color: var(--muted); }
.merge-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.merge-grid label { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
textarea { width: 100%; min-height: 360px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; line-height: 1.5; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); }
textarea[readonly] { background: var(--code-bg); color: var(--muted); }
.merge-tools { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.btn { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 8px; padding: 8px 16px; font: inherit; font-size: 14px; cursor: pointer; }
.btn.small { padding: 4px 10px; font-size: 13px; }
.btn.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
.btn:disabled { opacity: .5; cursor: default; }
details.rest { padding: 14px 20px; }
details.rest summary { cursor: pointer; color: var(--muted); font-size: 14px; }
details.rest ul { margin: 10px 0 0; padding-left: 18px; font-size: 13px; color: var(--muted); columns: 2; }
.empty { padding: 18px 20px; color: var(--muted); font-size: 14px; }
footer { position: fixed; left: 0; right: 0; bottom: 0; background: var(--panel); border-top: 1px solid var(--line); }
.foot { max-width: 1180px; margin: 0 auto; padding: 14px 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.foot .sum { flex: 1; min-width: 200px; font-size: 14px; color: var(--muted); }
.error { color: var(--warn); font-size: 13px; width: 100%; }
.done { max-width: 560px; margin: 18vh auto; text-align: center; padding: 0 20px; }
.done h1 { color: var(--ok); }
.muted { color: var(--muted); }
.theme { float: right; }
@media (max-width: 760px) {
  main { padding: 20px 16px; }
  .merge-grid { grid-template-columns: 1fr; }
  /* 窄屏：表格改为卡片，每项上下排列 */
  table.list > thead { display: none; }
  table.list, table.list > tbody, table.list > tbody > tr, table.list > tbody > tr > td { display: block; width: 100%; }
  table.list > tbody > tr { padding: 12px 16px; border-bottom: 1px solid var(--line); }
  table.list > tbody > tr:last-child { border-bottom: none; }
  table.list > tbody > tr > td { border: 0; padding: 4px 0; }
  table.list > tbody > tr.detail { padding: 0; }
  table.list > tbody > tr.detail > td { padding: 12px; }
  .seg { display: flex; flex-wrap: wrap; width: 100%; }
  .seg button { flex: 1 1 auto; }
  .desc { max-width: none; }
  details.rest ul { columns: 1; }
}
</style>
</head>
<body>
<main id="app"></main>
<footer id="footer"></footer>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var items = DATA.items;
  var token = DATA.token;
  var conflicts = items.filter(function (i) { return i.status === "conflict"; });
  var foreign = items.filter(function (i) { return i.status === "foreign"; });
  var rest = items.filter(function (i) { return i.status !== "conflict" && i.status !== "foreign"; });
  var choice = {};   // id -> keep | replace | merge | disable
  var merged = {};   // id -> 合并编辑内容
  var open = {};     // id -> 是否展开对比
  conflicts.forEach(function (i) { choice[i.id] = "keep"; merged[i.id] = i.new_text; });
  foreign.forEach(function (i) { choice[i.id] = "keep"; });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function count(status) { return items.filter(function (i) { return i.status === status; }).length; }
  function toolLabel(t) { return t === "claude" ? "Claude Code" : t === "codex" ? "Codex" : t; }
  function kindLabel(i) { return i.kind === "rules" ? "全局规则" : "技能"; }
  function displayName(i) { return i.kind === "rules" ? i.dest_pretty.split("/").pop() : i.name; }

  function seg(id, options) {
    return '<div class="seg" role="group">' + options.map(function (o) {
      return '<button type="button" data-id="' + esc(id) + '" data-act="' + o[0] + '" aria-pressed="' +
        (choice[id] === o[0]) + '">' + esc(o[1]) + "</button>";
    }).join("") + "</div>";
  }

  function conflictRows(i) {
    var row = '<tr>' +
      '<td><span class="tag">' + esc(toolLabel(i.tool)) + '</span></td>' +
      '<td><div class="name">' + esc(displayName(i)) + '</div><div class="meta">' + esc(kindLabel(i)) + '</div></td>' +
      '<td><div class="path">' + esc(i.dest_pretty) + '</div><div class="meta">' + esc(i.dest_info) + '</div></td>' +
      '<td>' + seg(i.id, [["keep", "保留原来的"], ["replace", "替换为 agent-kit"], ["merge", "合并编辑"]]) +
      '<div><button type="button" class="link" data-toggle="' + esc(i.id) + '">' +
      (open[i.id] ? "收起对比" : "展开对比") + "</button></div></td></tr>";
    if (!open[i.id] && choice[i.id] !== "merge") return row;
    var d = '<tr class="detail"><td colspan="4">';
    if (i.notes && i.notes.length) {
      d += '<ul class="notes">' + i.notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
    }
    d += '<div class="legend"><span class="l-sub">只在你原来的</span><span class="l-add">只在 agent-kit</span><span class="l-chg">两边都有但不同</span></div>';
    d += '<div class="diffbox">' + i.diff_html + "</div>";
    if (choice[i.id] === "merge") {
      d += '<div class="merge"><h3>合并编辑</h3>' +
        '<p>右边是将要使用的内容，直接编辑。保存后会写回 agent-kit 仓库的 <span class="path">' + esc(i.kit_file) +
        '</span>，所有电脑拉取后都会用到，记得提交到 GitHub。</p>' +
        '<div class="merge-grid"><div><label>你原来的（只读，可复制）</label><textarea readonly>' + esc(i.old_text) +
        '</textarea></div><div><label for="m' + esc(i.id) + '">合并后的内容</label><textarea id="m' + esc(i.id) +
        '" data-merge="' + esc(i.id) + '">' + esc(merged[i.id]) + "</textarea>" +
        '<div class="merge-tools"><button type="button" class="btn small" data-append="' + esc(i.id) +
        '">把原来的内容追加到末尾</button><button type="button" class="btn small" data-reset="' + esc(i.id) +
        '">恢复为 agent-kit 版本</button></div></div></div></div>';
    }
    return row + d + "</td></tr>";
  }

  function foreignRow(i) {
    return '<tr>' +
      '<td><span class="tag">' + esc(toolLabel(i.tool)) + '</span></td>' +
      '<td><div class="name">' + esc(i.name) + '</div><div class="desc">' + esc(i.description || "（没有描述）") + '</div></td>' +
      '<td><div class="path">' + esc(i.dest_pretty) + '</div><div class="meta">' + esc(i.dest_info) + '</div></td>' +
      '<td>' + seg(i.id, [["keep", "保留"], ["disable", "停用（移到备份）"]]) + "</td></tr>";
  }

  function render() {
    var h = '<button type="button" class="btn small theme" id="theme">切换深浅色</button>';
    h += "<h1>安装前检查</h1>";
    h += '<p class="lead">下面这些位置已经有内容，不是 agent-kit 装的。逐项决定怎么处理，最后点“应用”。被替换或停用的内容都会先备份。</p>';
    h += '<div class="chips">' +
      '<span class="chip' + (conflicts.length ? " hot" : "") + '">冲突<b>' + conflicts.length + "</b></span>" +
      '<span class="chip">其他来源技能<b>' + foreign.length + "</b></span>" +
      '<span class="chip">新增<b>' + count("new") + "</b></span>" +
      '<span class="chip">更新<b>' + count("update") + "</b></span>" +
      '<span class="chip">已是最新<b>' + count("uptodate") + "</b></span></div>";

    h += '<section><div class="sec-head"><h2>冲突（' + conflicts.length + '）</h2>' +
      '<p>同一个位置已有你自己的文件。保留：不装 agent-kit 的这一项；替换：旧的移到备份再安装；合并编辑：在下面编辑出最终内容，写回 agent-kit 后安装。</p></div>';
    if (conflicts.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>工具</th><th>名称</th><th>位置</th><th>处理方式</th></tr></thead><tbody>' +
        conflicts.map(conflictRows).join("") + "</tbody></table></div>";
    } else {
      h += '<div class="empty">没有冲突。</div>';
    }
    h += "</section>";

    h += '<section><div class="sec-head"><h2>其他来源的技能（' + foreign.length + '）</h2>' +
      '<p>这些技能不是 agent-kit 装的，名字也不同，但功能可能和通用技能重叠，导致两个都被触发。看描述决定是否停用。</p></div>';
    if (foreign.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>工具</th><th>名称与描述</th><th>位置</th><th>处理方式</th></tr></thead><tbody>' +
        foreign.map(foreignRow).join("") + "</tbody></table></div>";
    } else {
      h += '<div class="empty">没有其他来源的技能。</div>';
    }
    h += "</section>";

    h += '<section><details class="rest"><summary>其余 ' + rest.length + " 项会直接安装或更新，不需要处理</summary><ul>" +
      rest.map(function (i) {
        return "<li>" + esc(toolLabel(i.tool)) + " · " + esc(displayName(i)) + " · " + esc(i.status_label) + "</li>";
      }).join("") + "</ul></details></section>";

    document.getElementById("app").innerHTML = h;
    renderFooter();
  }

  function renderFooter(error) {
    var n = { keep: 0, replace: 0, merge: 0, disable: 0 };
    Object.keys(choice).forEach(function (k) { n[choice[k]]++; });
    var keepConflicts = conflicts.filter(function (i) { return choice[i.id] === "keep"; }).length;
    var parts = [];
    if (conflicts.length) parts.push("替换 " + n.replace + "，合并 " + n.merge + "，保留 " + keepConflicts);
    if (foreign.length) parts.push("停用 " + n.disable);
    document.getElementById("footer").innerHTML = '<div class="foot"><div class="sum">' +
      esc(parts.join("；") || "没有需要决定的项目") + "</div>" +
      '<button type="button" class="btn" id="cancel">取消</button>' +
      '<button type="button" class="btn primary" id="apply">应用</button>' +
      (error ? '<div class="error" role="alert">' + esc(error) + "</div>" : "") + "</div>";
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Token": token },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  function finish(title, text) {
    document.getElementById("footer").innerHTML = "";
    document.getElementById("app").innerHTML = '<div class="done"><h1>' + esc(title) + "</h1><p>" + esc(text) + "</p></div>";
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t.dataset.act) {
      choice[t.dataset.id] = t.dataset.act;
      if (t.dataset.act === "merge") open[t.dataset.id] = true;
      render();
    } else if (t.dataset.toggle) {
      open[t.dataset.toggle] = !open[t.dataset.toggle];
      render();
    } else if (t.dataset.append) {
      var it = conflicts.filter(function (i) { return i.id === t.dataset.append; })[0];
      merged[it.id] = (merged[it.id] || "").replace(/\s*$/, "") + "\n\n<!-- 以下为原来的内容 -->\n" + it.old_text;
      render();
    } else if (t.dataset.reset) {
      var it2 = conflicts.filter(function (i) { return i.id === t.dataset.reset; })[0];
      merged[it2.id] = it2.new_text;
      render();
    } else if (t.id === "theme") {
      var root = document.documentElement;
      var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
    } else if (t.id === "cancel") {
      post("/cancel").then(function () { finish("已取消", "没有改动任何文件，可以关闭这个页面。"); });
    } else if (t.id === "apply") {
      t.disabled = true;
      var m = {};
      Object.keys(choice).forEach(function (k) { if (choice[k] === "merge") m[k] = merged[k]; });
      post("/apply", { decisions: choice, merges: m }).then(function (r) {
        if (r.ok) finish("已提交", "回到终端查看安装结果，可以关闭这个页面。");
        else renderFooter(r.body.error || "提交失败");
      }).catch(function () { renderFooter("连接不上本地安装程序，它可能已经退出。"); });
    }
  });

  document.addEventListener("input", function (e) {
    if (e.target.dataset.merge) merged[e.target.dataset.merge] = e.target.value;
  });

  render();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
