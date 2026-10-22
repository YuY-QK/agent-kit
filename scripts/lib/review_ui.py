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


def mark_pair(a, b):
    """对一对相似的行做字符级比较，返回两边带 <mark> 的 HTML。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.ratio() < 0.35:
        return html.escape(a), html.escape(b)
    left, right = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        x, y = html.escape(a[i1:i2]), html.escape(b[j1:j2])
        if tag == "equal":
            left.append(x)
            right.append(y)
        else:
            if x:
                left.append("<mark>" + x + "</mark>")
            if y:
                right.append("<mark>" + y + "</mark>")
    return "".join(left), "".join(right)


def segments(old, new):
    """把两份文本拆成“相同段”和“差异块”，类似 git 的冲突块。

    返回列表，每项为：
      {"t": "eq", "a": 左起始行号, "b": 右起始行号, "lines": [...]}
      {"t": "ch", "a": ..., "b": ..., "left": [...], "right": [...], "lh": [...], "rh": [...]}
    其中 lh/rh 是带行内高亮的 HTML（已转义）。
    """
    a = old.splitlines()
    b = new.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append({"t": "eq", "a": i1 + 1, "b": j1 + 1, "lines": a[i1:i2]})
            continue
        # 相邻的删除和插入合并成同一个差异块
        if out and out[-1]["t"] == "ch":
            block = out[-1]
            block["left"].extend(a[i1:i2])
            block["right"].extend(b[j1:j2])
        else:
            out.append({"t": "ch", "a": i1 + 1, "b": j1 + 1, "left": a[i1:i2], "right": b[j1:j2]})
    for block in out:
        if block["t"] != "ch":
            continue
        lh = [html.escape(x) for x in block["left"]]
        rh = [html.escape(x) for x in block["right"]]
        for k in range(min(len(lh), len(rh))):
            lh[k], rh[k] = mark_pair(block["left"][k], block["right"][k])
        block["lh"] = lh
        block["rh"] = rh
    return out


def diff_stats(segs):
    hunks = [s for s in segs if s["t"] == "ch"]
    return {
        "hunks": len(hunks),
        "removed": sum(len(s["left"]) for s in hunks),
        "added": sum(len(s["right"]) for s in hunks),
    }


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
            text = read_text(main_file(item["dest"]))
            item["description"] = description_of(text or "")
            item["content"] = text if text is not None else "（无法读取内容）"
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
        if old is not None:
            item["segments"] = segments(old, new)
            item["stats"] = diff_stats(item["segments"])
        else:
            item["segments"] = []
            item["stats"] = None
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
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  padding-bottom: 110px;
}
main { max-width: 1240px; margin: 0 auto; padding: 32px 20px; }
h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -.01em; }
h2 { font-size: 17px; margin: 0; }
.lead { color: var(--muted); margin: 0 0 18px; max-width: 820px; }
.mono, .path, .code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.chip { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 3px 12px; font-size: 13px; color: var(--muted); }
.chip b { color: var(--ink); font-weight: 600; margin-left: 4px; }
.chip.hot { border-color: var(--warn); color: var(--warn); background: var(--warn-bg); }
.chip.hot b { color: var(--warn); }
.legend-box { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: var(--muted); margin: -8px 0 22px; }
.legend-box .sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 6px; }
.sw.l { background: var(--left-bg); border: 1px solid var(--left); }
.sw.r { background: var(--right-bg); border: 1px solid var(--right); }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); margin-bottom: 20px; overflow: hidden; }
.sec-head { padding: 16px 20px; border-bottom: 1px solid var(--line); }
.sec-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.table-wrap { overflow-x: auto; }
table.list { width: 100%; border-collapse: collapse; }
table.list > thead > tr > th { text-align: left; padding: 10px 16px; font-size: 12px; color: var(--muted); font-weight: 500; background: var(--code-bg); border-bottom: 1px solid var(--line); white-space: nowrap; }
table.list > tbody > tr > td { text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--line); vertical-align: top; }
table.list > tbody > tr:last-child > td { border-bottom: none; }
tr.row-open > td { background: var(--accent-soft); }
.name { font-weight: 600; }
.path { font-size: 12.5px; color: var(--muted); word-break: break-all; }
.meta { font-size: 12px; color: var(--muted); }
.desc { font-size: 13px; color: var(--muted); max-width: 380px; }
.tag { display: inline-block; font-size: 12px; border-radius: 6px; padding: 1px 8px; background: var(--code-bg); border: 1px solid var(--line); color: var(--muted); white-space: nowrap; }
.stat { font-size: 13px; white-space: nowrap; }
.stat .minus { color: var(--left); } .stat .plus { color: var(--right); }
.badge { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; white-space: nowrap; border: 1px solid transparent; }
.badge.todo { color: var(--warn); background: var(--warn-bg); border-color: var(--warn); }
.badge.done { color: var(--ok); background: var(--ok-bg); }
.badge.doing { color: var(--accent); background: var(--accent-soft); }
.ops { display: flex; flex-wrap: wrap; gap: 6px; }
.op { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 7px; padding: 5px 10px; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
.op:hover:not(:disabled) { border-color: var(--accent); }
.op[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.op.l[aria-pressed="true"] { background: var(--left); border-color: var(--left); color: #fff; }
.op.r[aria-pressed="true"] { background: var(--right); border-color: var(--right); color: #fff; }
.op:disabled { opacity: .45; cursor: not-allowed; }
.op.ghost { border-color: transparent; background: transparent; color: var(--accent); padding-left: 4px; padding-right: 4px; }
button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
tr.detail > td { background: var(--code-bg); padding: 0 !important; }
.panel { padding: 16px; }
.notes { margin: 0 0 12px; padding: 10px 14px; border-radius: 8px; background: var(--panel); border: 1px dashed var(--line); font-size: 13px; color: var(--muted); }
.notes div + div { margin-top: 4px; }
.toolbar { position: sticky; top: 0; z-index: 3; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 12px; margin: 0 0 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
.toolbar .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
.progress { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); margin-right: auto; }
.bar { width: 110px; height: 6px; border-radius: 999px; background: var(--line); overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--ok); }
.cols { display: block; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--panel); }
.colrow { display: grid; grid-template-columns: 1fr 1fr; position: sticky; top: 0; z-index: 2; }
.colhead { padding: 8px 12px; font-size: 12px; font-weight: 600; border-bottom: 1px solid var(--line); }
.colhead.l { color: var(--left); background: var(--left-bg); }
.colhead.r { color: var(--right); background: var(--right-bg); border-left: 1px solid var(--line); }
.seg { display: grid; grid-template-columns: 1fr 1fr; }
.side { min-width: 0; }
.side + .side { border-left: 1px solid var(--line); }
.ln { display: grid; grid-template-columns: 44px 1fr; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; line-height: 1.55; }
.ln .no { color: var(--faint); text-align: right; padding: 0 8px 0 0; user-select: none; }
.ln .tx { white-space: pre-wrap; word-break: break-all; padding-right: 10px; min-height: 1.55em; }
.eq .ln .tx { color: var(--muted); }
.fold { text-align: center; border-top: 1px dashed var(--line); border-bottom: 1px dashed var(--line); background: var(--code-bg); }
.fold button { border: 0; background: none; color: var(--accent); font: inherit; font-size: 12.5px; padding: 4px 10px; cursor: pointer; }
.hunk { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); scroll-margin-top: 80px; }
.hunk.todo { box-shadow: inset 3px 0 0 var(--warn); }
.hunk.cur { outline: 2px solid var(--accent); outline-offset: -2px; }
.hhead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 10px; background: var(--code-bg); border-bottom: 1px solid var(--line); }
.hhead .htitle { font-size: 12.5px; font-weight: 600; margin-right: 6px; }
.hhead .ops { margin-left: auto; }
.hbody { display: grid; grid-template-columns: 1fr 1fr; }
.hbody .side.l { background: var(--left-bg); }
.hbody .side.r { background: var(--right-bg); }
.hbody .side.dim { opacity: .38; }
.hbody .side.pick { box-shadow: inset 0 0 0 2px var(--accent); opacity: 1; }
.hbody mark { border-radius: 2px; color: inherit; padding: 0 1px; }
.hbody .side.l mark { background: var(--left-mark); }
.hbody .side.r mark { background: var(--right-mark); }
.empty-side { padding: 4px 10px; font-size: 12px; color: var(--faint); font-style: italic; }
.order { padding: 6px 12px; font-size: 12px; color: var(--accent); background: var(--accent-soft); border-top: 1px solid var(--line); }
.custom { padding: 10px 12px; border-top: 1px solid var(--line); background: var(--panel); }
.custom label { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
textarea { width: 100%; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; line-height: 1.55; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); }
.custom textarea { min-height: 120px; }
.custom .ops { margin-top: 8px; }
.result { margin-top: 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); overflow: hidden; }
.result summary { cursor: pointer; padding: 10px 12px; font-size: 13px; font-weight: 600; background: var(--code-bg); border-bottom: 1px solid var(--line); }
.result summary span { font-weight: 400; color: var(--muted); }
.result .rbody { max-height: 420px; overflow: auto; padding: 6px 0; }
.result .ln.mk .tx { background: var(--marker-bg); color: var(--warn); font-weight: 600; }
.result textarea { border: 0; border-radius: 0; min-height: 360px; }
.result .rfoot { padding: 8px 12px; border-top: 1px solid var(--line); font-size: 12.5px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { font-size: 13px; color: var(--muted); margin: 0 0 12px; }
.hint.warn { color: var(--warn); }
pre.content { margin: 0; padding: 12px 14px; max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-all; font-size: 12.5px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
details.rest { padding: 14px 20px; }
details.rest summary { cursor: pointer; color: var(--muted); font-size: 14px; }
details.rest ul { margin: 10px 0 0; padding-left: 18px; font-size: 13px; color: var(--muted); columns: 2; }
.empty { padding: 18px 20px; color: var(--muted); font-size: 14px; }
footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 5; background: var(--panel); border-top: 1px solid var(--line); }
.foot { max-width: 1240px; margin: 0 auto; padding: 12px 20px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.foot .sum { flex: 1; min-width: 220px; font-size: 14px; }
.foot .sum small { display: block; color: var(--muted); font-size: 12.5px; }
.btn { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 8px; padding: 8px 16px; font: inherit; font-size: 14px; cursor: pointer; }
.btn.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.error { color: var(--warn); font-size: 13px; width: 100%; }
.finished { max-width: 560px; margin: 18vh auto; text-align: center; padding: 0 20px; }
.finished h1 { color: var(--ok); }
.topbar { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
kbd { font-family: ui-monospace, Menlo, monospace; font-size: 11px; border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 4px; background: var(--code-bg); }
@media (max-width: 820px) {
  main { padding: 20px 16px; }
  table.list > thead { display: none; }
  table.list, table.list > tbody, table.list > tbody > tr, table.list > tbody > tr > td { display: block; width: 100%; }
  table.list > tbody > tr { padding: 12px 16px; border-bottom: 1px solid var(--line); }
  table.list > tbody > tr:last-child { border-bottom: none; }
  table.list > tbody > tr > td { border: 0 !important; padding: 3px 0; }
  table.list > tbody > tr.detail { padding: 0; }
  .colrow, .seg, .hbody { grid-template-columns: 1fr; }
  .colhead.r, .side + .side { border-left: 0; border-top: 1px solid var(--line); }
  .hhead .ops { margin-left: 0; }
  .toolbar { position: static; }
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
  var items = DATA.items, token = DATA.token;
  var conflicts = items.filter(function (i) { return i.status === "conflict"; });
  var foreign = items.filter(function (i) { return i.status === "foreign"; });
  var rest = items.filter(function (i) { return i.status !== "conflict" && i.status !== "foreign"; });
  var byId = {};
  items.forEach(function (i) { byId[i.id] = i; });

  var LEFT = "你原来的", RIGHT = "agent-kit";
  var RES_LABEL = { left: "已接受左侧", right: "已接受右侧", lr: "两者（左在前）", rl: "两者（右在前）", none: "两侧都不要", custom: "已手动编辑" };

  // ---- 状态 ----
  // 冲突：mode = null 未处理 / left 整个接受左侧 / right 整个接受右侧 / merge 逐块合并
  var S = {};
  conflicts.forEach(function (i) {
    var hunks = [];
    i.segments.forEach(function (sg) { if (sg.t === "ch") { sg.h = hunks.length; hunks.push({ res: null, custom: "", editing: false }); } });
    S[i.id] = { mode: null, open: false, hunks: hunks, manual: false, manualText: "", fold: {}, cur: -1 };
  });
  var F = {};  // 其他来源技能：keep / disable，show 是否展开内容
  foreign.forEach(function (i) { F[i.id] = { act: "keep", show: false }; });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function toolLabel(t) { return t === "claude" ? "Claude Code" : t === "codex" ? "Codex" : t; }
  function kindLabel(i) { return i.kind === "rules" ? "全局规则" : "技能"; }
  function displayName(i) { return i.kind === "rules" ? i.dest_pretty.split("/").pop() : i.name; }

  // ---- 合并计算 ----
  function hunkLines(sg, h) {
    switch (h.res) {
      case "left": return sg.left;
      case "right": return sg.right;
      case "lr": return sg.left.concat(sg.right);
      case "rl": return sg.right.concat(sg.left);
      case "none": return [];
      case "custom": return h.custom === "" ? [] : h.custom.split("\n");
      default: return null;
    }
  }
  // withMarkers：未处理的块用 git 冲突标记表示
  function composeLines(i, withMarkers) {
    var st = S[i.id], out = [];
    i.segments.forEach(function (sg) {
      if (sg.t === "eq") { out = out.concat(sg.lines.map(function (x) { return { t: x }; })); return; }
      var lines = hunkLines(sg, st.hunks[sg.h]);
      if (lines) { out = out.concat(lines.map(function (x) { return { t: x }; })); return; }
      if (!withMarkers) return;
      out.push({ t: "<<<<<<< " + LEFT, mk: true });
      out = out.concat(sg.left.map(function (x) { return { t: x }; }));
      out.push({ t: "=======", mk: true });
      out = out.concat(sg.right.map(function (x) { return { t: x }; }));
      out.push({ t: ">>>>>>> " + RIGHT, mk: true });
    });
    return out;
  }
  function composedText(i) {
    return composeLines(i, false).map(function (x) { return x.t; }).join("\n") + "\n";
  }
  function finalText(i) { return S[i.id].manual ? S[i.id].manualText : composedText(i); }
  function doneHunks(i) { return S[i.id].hunks.filter(function (h) { return h.res !== null; }).length; }
  function isResolved(i) {
    var st = S[i.id];
    if (st.mode === "left" || st.mode === "right") return true;
    if (st.mode === "merge") return st.manual || doneHunks(i) === st.hunks.length;
    return false;
  }
  function norm(t) { return (t || "").replace(/\s+$/, ""); }

  function statusBadge(i) {
    var st = S[i.id];
    if (st.mode === "left") return '<span class="badge done">保留原来的</span>';
    if (st.mode === "right") return '<span class="badge done">使用 agent-kit</span>';
    if (st.mode === "merge") {
      if (st.manual) return '<span class="badge done">已手动编辑结果</span>';
      var d = doneHunks(i), n = st.hunks.length;
      return d === n ? '<span class="badge done">已合并</span>' : '<span class="badge doing">合并中 ' + d + "/" + n + "</span>";
    }
    return '<span class="badge todo">未处理</span>';
  }

  // ---- 渲染：冲突表格 ----
  function conflictRow(i) {
    var st = S[i.id], s = i.stats;
    var stat = s ? '<span class="stat"><span class="minus">−' + s.removed + '</span> <span class="plus">+' + s.added +
      "</span><br><span class=\"meta\">" + s.hunks + " 处差异</span></span>" : '<span class="meta">无法比较</span>';
    var canMerge = i.old_readable && i.segments.length;
    var ops = '<div class="ops">' +
      '<button type="button" class="op l" data-mode="left" data-id="' + i.id + '" aria-pressed="' + (st.mode === "left") + '" title="保留你原来的文件，不安装 agent-kit 的这一项">接受左侧</button>' +
      '<button type="button" class="op r" data-mode="right" data-id="' + i.id + '" aria-pressed="' + (st.mode === "right") + '" title="原来的文件先备份，再安装 agent-kit 的版本">接受右侧</button>' +
      '<button type="button" class="op" data-mode="merge" data-id="' + i.id + '" aria-pressed="' + (st.mode === "merge") + '"' +
      (canMerge ? "" : " disabled") + ' title="逐块选择保留哪一边，结果写回 agent-kit 仓库">逐块合并</button>' +
      '<button type="button" class="op ghost" data-open="' + i.id + '">' + (st.open ? "收起" : (st.mode === "merge" ? "继续合并" : "查看差异")) + "</button></div>";
    var row = '<tr class="' + (st.open ? "row-open" : "") + '" id="row-' + i.id + '">' +
      '<td><span class="tag">' + esc(toolLabel(i.tool)) + "</span></td>" +
      '<td><div class="name">' + esc(displayName(i)) + '</div><div class="meta">' + esc(kindLabel(i)) + "</div></td>" +
      '<td><div class="path">' + esc(i.dest_pretty) + '</div><div class="meta">' + esc(i.dest_info) + "</div></td>" +
      "<td>" + stat + "</td><td>" + statusBadge(i) + "</td><td>" + ops + "</td></tr>";
    if (!st.open) return row;
    return row + '<tr class="detail"><td colspan="6">' + mergePanel(i) + "</td></tr>";
  }

  function lineHTML(no, html, cls) {
    return '<div class="ln' + (cls ? " " + cls : "") + '"><span class="no">' + (no == null ? "" : no) + '</span><span class="tx">' + html + "</span></div>";
  }
  function sideLines(lines, start, isHtml) {
    if (!lines.length) return '<div class="empty-side">（这一侧没有内容）</div>';
    return lines.map(function (x, k) { return lineHTML(start + k, isHtml ? x : esc(x)); }).join("");
  }

  function mergePanel(i) {
    var st = S[i.id], merging = st.mode === "merge";
    var h = '<div class="panel">';
    if (i.notes && i.notes.length) {
      h += '<div class="notes">' + i.notes.map(function (n) { return "<div>" + esc(n) + "</div>"; }).join("") +
        "<div>逐块合并只处理 SKILL.md；接受右侧时整个文件夹会被替换，原来的文件夹完整备份。</div></div>";
    }
    if (!i.old_readable) {
      return h + '<p class="hint warn">原来的内容不是可读的文本文件（可能是失效的链接），只能整个接受左侧或右侧。</p></div>';
    }
    if (!merging) {
      h += '<p class="hint">下面是两边的差异。选择上方的“逐块合并”后，可以对每一块分别处理。</p>';
    }
    if (merging) h += toolbar(i);
    if (merging && st.manual) {
      h += '<p class="hint">你正在直接编辑最终结果，逐块操作已暂停。点“放弃手动修改”可回到逐块处理。</p>';
    }
    h += '<div class="cols"><div class="colrow"><div class="colhead l">左侧 · ' + LEFT + "（" + esc(i.dest_pretty) + "）</div>" +
      '<div class="colhead r">右侧 · ' + RIGHT + "（" + esc(i.kit_file) + "）</div></div>";
    var n = 0, total = st.hunks.length;
    i.segments.forEach(function (sg, k) {
      if (sg.t === "eq") { h += eqBlock(i, sg, k); return; }
      n++;
      h += hunkBlock(i, sg, n, total, merging && !st.manual);
    });
    h += "</div>";
    if (merging) h += resultBox(i);
    return h + "</div>";
  }

  function toolbar(i) {
    var st = S[i.id], d = doneHunks(i), n = st.hunks.length, pct = n ? Math.round(d * 100 / n) : 100;
    var dis = st.manual ? " disabled" : "";
    var h = '<div class="toolbar"><div class="progress"><span>已处理 <b>' + d + "</b> / " + n + ' 处</span><span class="bar"><i style="width:' + pct + '%"></i></span></div>' +
      '<button type="button" class="op" data-nav="prev" data-id="' + i.id + '"' + dis + ">上一处未处理</button>" +
      '<button type="button" class="op" data-nav="next" data-id="' + i.id + '"' + dis + ">下一处未处理</button>" +
      '<span class="sep"></span>' +
      '<button type="button" class="op l" data-all="left" data-id="' + i.id + '"' + dis + ">剩余全部接受左侧</button>" +
      '<button type="button" class="op r" data-all="right" data-id="' + i.id + '"' + dis + ">剩余全部接受右侧</button>" +
      '<button type="button" class="op" data-reset="' + i.id + '"' + dis + ">重置</button>" +
      '<span class="sep"></span>' +
      '<button type="button" class="op" data-manual="' + i.id + '" aria-pressed="' + st.manual + '">' + (st.manual ? "放弃手动修改" : "直接编辑结果") + "</button>";
    // 两个工具共用同一份 agent-kit 文件时，可以套用另一处的合并结果
    conflicts.forEach(function (o) {
      if (o.id !== i.id && o.kit_file === i.kit_file && S[o.id].mode === "merge" && isResolved(o)) {
        h += '<button type="button" class="op" data-copy-from="' + o.id + '" data-id="' + i.id + '">套用 ' + esc(toolLabel(o.tool)) + " 的合并结果</button>";
      }
    });
    return h + "</div>";
  }

  function eqBlock(i, sg, k) {
    var st = S[i.id], lines = sg.lines, show;
    function both(from, to) {
      var l = "", r = "";
      for (var x = from; x < to; x++) { l += lineHTML(sg.a + x, esc(lines[x])); r += lineHTML(sg.b + x, esc(lines[x])); }
      return '<div class="seg eq"><div class="side">' + l + '</div><div class="side">' + r + "</div></div>";
    }
    if (lines.length <= 8 || st.fold[k]) return both(0, lines.length);
    show = both(0, 3) + '<div class="fold"><button type="button" data-fold="' + k + '" data-id="' + i.id + '">展开 ' + (lines.length - 6) + " 行相同内容</button></div>" +
      both(lines.length - 3, lines.length);
    return show;
  }

  function hunkBlock(i, sg, n, total, active) {
    var st = S[i.id], hk = st.hunks[sg.h], res = hk.res;
    var leftCls = "side l", rightCls = "side r";
    if (res === "left") { leftCls += " pick"; rightCls += " dim"; }
    if (res === "right") { rightCls += " pick"; leftCls += " dim"; }
    if (res === "lr" || res === "rl") { leftCls += " pick"; rightCls += " pick"; }
    if (res === "none" || res === "custom") { leftCls += " dim"; rightCls += " dim"; }
    var cls = "hunk" + (res === null && active ? " todo" : "") + (st.cur === sg.h ? " cur" : "");
    var h = '<div class="' + cls + '" id="hunk-' + i.id + "-" + sg.h + '"><div class="hhead"><span class="htitle">差异 ' + n + " / " + total + "</span>" +
      (st.mode === "merge" && st.manual ? '<span class="badge doing">由直接编辑的结果决定</span>' :
        res === null ? '<span class="badge todo">未处理</span>' : '<span class="badge done">' + esc(RES_LABEL[res]) + "</span>");
    if (active) {
      var b = function (r, label, extra, title) {
        return '<button type="button" class="op' + (extra || "") + '" data-res="' + r + '" data-id="' + i.id + '" data-h="' + sg.h + '" aria-pressed="' + (res === r) + '" title="' + title + '">' + label + "</button>";
      };
      h += '<div class="ops">' +
        b("left", "接受左侧", " l", "这一块用你原来的") +
        b("right", "接受右侧", " r", "这一块用 agent-kit 的") +
        b("lr", "两者都要 · 左在前", "", "先放你原来的，再放 agent-kit 的") +
        b("rl", "两者都要 · 右在前", "", "先放 agent-kit 的，再放你原来的") +
        b("none", "都不要", "", "这一块两边都删掉") +
        '<button type="button" class="op" data-edit="' + sg.h + '" data-id="' + i.id + '" aria-pressed="' + (res === "custom") + '" title="手动写这一块的内容">编辑…</button>' +
        (res !== null ? '<button type="button" class="op ghost" data-res="clear" data-id="' + i.id + '" data-h="' + sg.h + '">撤销</button>' : "") +
        "</div>";
    }
    h += '</div><div class="hbody"><div class="' + leftCls + '">' + sideLines(sg.lh, sg.a, true) + '</div><div class="' + rightCls + '">' + sideLines(sg.rh, sg.b, true) + "</div></div>";
    if (res === "lr") h += '<div class="order">结果中：先放左侧（你原来的），再放右侧（agent-kit）</div>';
    if (res === "rl") h += '<div class="order">结果中：先放右侧（agent-kit），再放左侧（你原来的）</div>';
    if (hk.editing) {
      h += '<div class="custom"><label for="ed-' + i.id + "-" + sg.h + '">手动编辑这一块（会替换掉这一块的两侧内容）</label>' +
        '<textarea id="ed-' + i.id + "-" + sg.h + '" data-edit-text="' + sg.h + '" data-id="' + i.id + '">' + esc(hk.draft) + "</textarea>" +
        '<div class="ops"><button type="button" class="op" aria-pressed="true" data-edit-ok="' + sg.h + '" data-id="' + i.id + '">完成</button>' +
        '<button type="button" class="op" data-edit-cancel="' + sg.h + '" data-id="' + i.id + '">取消</button></div></div>';
    } else if (res === "custom") {
      h += '<div class="custom"><label>这一块的手动内容</label><pre class="content">' + esc(hk.custom || "（空）") + "</pre></div>";
    }
    return h + "</div>";
  }

  function resultBox(i) {
    var st = S[i.id];
    var h = '<details class="result" open><summary>合并结果预览 <span>· 应用后写回 ' + esc(i.kit_file) + "，再安装到 " + esc(i.dest_pretty) + "</span></summary>";
    if (st.manual) {
      h += '<textarea id="man-' + i.id + '" data-manual-text="' + i.id + '">' + esc(st.manualText) + "</textarea>";
    } else {
      h += '<div class="rbody" id="pv-' + i.id + '">' + previewHTML(i) + "</div>";
    }
    h += '<div class="rfoot">' + (st.manual ? "直接编辑的内容会作为最终结果。" :
      "黄色的 <span class=\"mono\">&lt;&lt;&lt;&lt;&lt;&lt;&lt;</span> / <span class=\"mono\">&gt;&gt;&gt;&gt;&gt;&gt;&gt;</span> 是还没处理的块，全部处理后才能应用。") +
      " 写回 agent-kit 后，其他电脑 git pull 也会用上，记得提交。</div></details>";
    return h;
  }
  function previewHTML(i) {
    return composeLines(i, true).map(function (x, k) { return lineHTML(k + 1, esc(x.t), x.mk ? "mk" : ""); }).join("");
  }

  // ---- 渲染：其他来源技能 ----
  function foreignRow(i) {
    var f = F[i.id];
    var row = '<tr class="' + (f.show ? "row-open" : "") + '"><td><span class="tag">' + esc(toolLabel(i.tool)) + "</span></td>" +
      '<td><div class="name">' + esc(i.name) + '</div><div class="desc">' + esc(i.description || "（没有描述）") + "</div></td>" +
      '<td><div class="path">' + esc(i.dest_pretty) + '</div><div class="meta">' + esc(i.dest_info) + "</div></td>" +
      "<td>" + (f.act === "disable" ? '<span class="badge doing">将停用</span>' : '<span class="badge done">保留</span>') + "</td>" +
      '<td><div class="ops"><button type="button" class="op" data-fact="keep" data-id="' + i.id + '" aria-pressed="' + (f.act === "keep") + '">保留</button>' +
      '<button type="button" class="op" data-fact="disable" data-id="' + i.id + '" aria-pressed="' + (f.act === "disable") + '" title="移到备份目录，工具不再加载">停用（移到备份）</button>' +
      '<button type="button" class="op ghost" data-fshow="' + i.id + '">' + (f.show ? "收起" : "查看内容") + "</button></div></td></tr>";
    if (!f.show) return row;
    return row + '<tr class="detail"><td colspan="5"><div class="panel"><pre class="content">' + esc(i.content) + "</pre></div></td></tr>";
  }

  function render() {
    var y = window.scrollY;
    var resolved = conflicts.filter(isResolved).length;
    var h = '<div class="topbar"><div><h1>安装前检查</h1>' +
      '<p class="lead">这些位置已经有内容，不是 agent-kit 装的。处理方式和 git 解决冲突一样：<b>左侧</b>是你原来的（当前），<b>右侧</b>是 agent-kit 的（传入）。可以整个文件接受某一侧，也可以逐块合并。被替换或停用的内容都会先备份。</p></div>' +
      '<button type="button" class="btn" id="theme">切换深浅色</button></div>';
    h += '<div class="chips"><span class="chip' + (resolved < conflicts.length ? " hot" : "") + '">冲突已处理<b>' + resolved + " / " + conflicts.length + "</b></span>" +
      '<span class="chip">其他来源技能<b>' + foreign.length + "</b></span>" +
      '<span class="chip">新增<b>' + rest.filter(function (i) { return i.status === "new"; }).length + "</b></span>" +
      '<span class="chip">更新<b>' + rest.filter(function (i) { return i.status === "update"; }).length + "</b></span>" +
      '<span class="chip">已是最新<b>' + rest.filter(function (i) { return i.status === "uptodate"; }).length + "</b></span></div>";
    h += '<div class="legend-box"><span><span class="sw l"></span>左侧 · 你原来的</span><span><span class="sw r"></span>右侧 · agent-kit</span><span>行内深色标记：这一行里具体不同的文字</span></div>';

    h += '<section><div class="sec-head"><h2>冲突（' + conflicts.length + "）</h2><p>接受左侧：保留你的文件，不安装这一项。接受右侧：你的文件先备份，再安装 agent-kit 的。逐块合并：对每一处差异分别选择，结果写回 agent-kit 仓库后安装。</p></div>";
    if (conflicts.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>工具</th><th>名称</th><th>位置</th><th>差异</th><th>状态</th><th>操作</th></tr></thead><tbody>' +
        conflicts.map(conflictRow).join("") + "</tbody></table></div>";
    } else {
      h += '<div class="empty">没有冲突。</div>';
    }
    h += "</section>";

    h += '<section><div class="sec-head"><h2>其他来源的技能（' + foreign.length + "）</h2><p>不是 agent-kit 装的，名字也不同，但功能可能和通用技能重叠，导致两个都被触发。默认保留，看内容决定是否停用。</p></div>";
    if (foreign.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>工具</th><th>名称与描述</th><th>位置</th><th>状态</th><th>操作</th></tr></thead><tbody>' +
        foreign.map(foreignRow).join("") + "</tbody></table></div>";
    } else {
      h += '<div class="empty">没有其他来源的技能。</div>';
    }
    h += "</section>";

    h += '<section><details class="rest"><summary>其余 ' + rest.length + " 项会直接安装或更新，不需要处理</summary><ul>" +
      rest.map(function (i) { return "<li>" + esc(toolLabel(i.tool)) + " · " + esc(displayName(i)) + " · " + esc(i.status_label) + "</li>"; }).join("") +
      "</ul></details></section>";

    document.getElementById("app").innerHTML = h;
    renderFooter();
    window.scrollTo(0, y);
  }

  function renderFooter(error) {
    var resolved = conflicts.filter(isResolved).length, left = conflicts.length - resolved;
    var c = { left: 0, right: 0, merge: 0 };
    conflicts.forEach(function (i) { if (S[i.id].mode && isResolved(i)) c[S[i.id].mode]++; });
    var dis = foreign.filter(function (i) { return F[i.id].act === "disable"; }).length;
    var sum = conflicts.length ? "冲突已处理 " + resolved + " / " + conflicts.length : "没有冲突";
    var detail = [];
    if (c.left) detail.push("保留原来的 " + c.left);
    if (c.right) detail.push("使用 agent-kit " + c.right);
    if (c.merge) detail.push("合并 " + c.merge);
    if (foreign.length) detail.push("停用其他技能 " + dis);
    document.getElementById("footer").innerHTML = '<div class="foot"><div class="sum">' + esc(sum) +
      "<small>" + esc(detail.join(" · ") || "逐项处理后点“应用”") + (left ? " · 还有 " + left + " 项未处理" : "") + "</small></div>" +
      (left ? '<button type="button" class="btn" id="keep-rest" title="把还没处理的冲突都设为接受左侧">剩余冲突全部接受左侧</button>' : "") +
      '<button type="button" class="btn" id="cancel">取消</button>' +
      '<button type="button" class="btn primary" id="apply"' + (left ? " disabled" : "") + ">应用</button>" +
      (error ? '<div class="error" role="alert">' + esc(error) + "</div>" : "") + "</div>";
  }

  function scrollToHunk(i, idx) {
    S[i.id].cur = idx;
    render();
    var el = document.getElementById("hunk-" + i.id + "-" + idx);
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  function nextTodo(i, dir) {
    var st = S[i.id], n = st.hunks.length;
    for (var step = 1; step <= n; step++) {
      var k = ((st.cur < 0 ? (dir > 0 ? -1 : 0) : st.cur) + dir * step + n * 2) % n;
      if (st.hunks[k].res === null) return k;
    }
    return -1;
  }

  // ---- 提交 ----
  function post(path, body) {
    return fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Token": token }, body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }
  function finish(title, text) {
    document.getElementById("footer").innerHTML = "";
    document.getElementById("app").innerHTML = '<div class="finished"><h1>' + esc(title) + "</h1><p>" + esc(text) + "</p></div>";
  }
  function buildPayload() {
    var decisions = {}, merges = {}, byFile = {};
    for (var k = 0; k < conflicts.length; k++) {
      var i = conflicts[k], st = S[i.id];
      if (st.mode === "left") decisions[i.id] = "keep";
      else if (st.mode === "right") decisions[i.id] = "replace";
      else {
        var text = finalText(i);
        if (norm(text) === norm(i.new_text)) { decisions[i.id] = "replace"; continue; }
        decisions[i.id] = "merge";
        merges[i.id] = text;
        if (byFile[i.kit_file] !== undefined && norm(byFile[i.kit_file].text) !== norm(text)) {
          return { error: displayName(i) + "（" + toolLabel(i.tool) + "）和" + byFile[i.kit_file].who + "共用同一份 agent-kit 文件，但两处合并结果不一样。可以在其中一处点“套用…的合并结果”。" };
        }
        byFile[i.kit_file] = { text: text, who: displayName(i) + "（" + toolLabel(i.tool) + "）" };
      }
    }
    foreign.forEach(function (i) { decisions[i.id] = F[i.id].act; });
    return { decisions: decisions, merges: merges };
  }

  // ---- 事件 ----
  var confirmMarkers = false;
  document.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (!t || t.disabled) return;
    var d = t.dataset, i = d.id ? byId[d.id] : null, st = i ? S[i.id] : null;

    if (d.mode) {
      st.mode = st.mode === d.mode ? null : d.mode;
      if (st.mode === "merge") st.open = true;
      return render();
    }
    if (d.open) { S[d.open].open = !S[d.open].open; return render(); }
    if (d.res) {
      var hk = st.hunks[+d.h];
      hk.res = d.res === "clear" ? null : d.res;
      hk.editing = false;
      st.cur = +d.h;
      render();
      if (d.res !== "clear") {
        var nx = nextTodo(i, 1);
        if (nx >= 0 && nx !== +d.h) {
          st.cur = nx;
          render();
          var el = document.getElementById("hunk-" + i.id + "-" + nx);
          if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }
      return;
    }
    if (d.edit !== undefined && d.edit !== "") {
      var hk2 = st.hunks[+d.edit], sg = i.segments.filter(function (x) { return x.t === "ch" && x.h === +d.edit; })[0];
      var cur = hunkLines(sg, hk2);
      hk2.draft = (cur ? cur : sg.left.concat(sg.right)).join("\n");
      hk2.editing = true;
      render();
      var ta = document.getElementById("ed-" + i.id + "-" + d.edit);
      if (ta) ta.focus();
      return;
    }
    if (d.editOk) { var a = st.hunks[+d.editOk]; a.custom = a.draft; a.res = "custom"; a.editing = false; return render(); }
    if (d.editCancel) { st.hunks[+d.editCancel].editing = false; return render(); }
    if (d.nav) {
      var k = nextTodo(i, d.nav === "next" ? 1 : -1);
      if (k >= 0) scrollToHunk(i, k);
      return;
    }
    if (d.all) { st.hunks.forEach(function (h) { if (h.res === null) h.res = d.all; }); return render(); }
    if (d.reset) { S[d.reset].hunks.forEach(function (h) { h.res = null; h.editing = false; }); S[d.reset].cur = -1; return render(); }
    if (d.manual) {
      var m = S[d.manual];
      if (m.manual) { m.manual = false; return render(); }
      m.manualText = composeLines(byId[d.manual], true).map(function (x) { return x.t; }).join("\n") + "\n";
      m.manual = true;
      return render();
    }
    if (d.copyFrom) {
      st.manualText = finalText(byId[d.copyFrom]);
      st.manual = true;
      return render();
    }
    if (d.fold) { st.fold[d.fold] = true; return render(); }
    if (d.fact) { F[d.id].act = d.fact; return render(); }
    if (d.fshow) { F[d.fshow].show = !F[d.fshow].show; return render(); }

    if (t.id === "theme") {
      var root = document.documentElement;
      var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      return;
    }
    if (t.id === "keep-rest") { conflicts.forEach(function (c) { if (!isResolved(c)) S[c.id].mode = "left"; }); return render(); }
    if (t.id === "cancel") {
      post("/cancel").then(function () { finish("已取消", "没有改动任何文件，可以关闭这个页面。"); });
      return;
    }
    if (t.id === "apply") {
      var manualMarkers = conflicts.filter(function (c) { return S[c.id].mode === "merge" && S[c.id].manual && /^(<{7}|={7}|>{7})( |$)/m.test(S[c.id].manualText); });
      if (manualMarkers.length && !confirmMarkers) {
        confirmMarkers = true;
        return renderFooter(displayName(manualMarkers[0]) + " 手动编辑的结果里还有冲突标记（<<<<<<< / ======= / >>>>>>>）。确定按原样应用，请再点一次“应用”。");
      }
      var p = buildPayload();
      if (p.error) return renderFooter(p.error);
      t.disabled = true;
      post("/apply", p).then(function (r) {
        if (r.ok) finish("已提交", "回到终端查看安装结果，可以关闭这个页面。");
        else renderFooter(r.body.error || "提交失败");
      }).catch(function () { renderFooter("连接不上本地安装程序，它可能已经退出。"); });
    }
  });

  document.addEventListener("input", function (e) {
    var d = e.target.dataset;
    confirmMarkers = false;
    if (d.editText !== undefined && d.editText !== "") { S[d.id].hunks[+d.editText].draft = e.target.value; }
    if (d.manualText) { S[d.manualText].manualText = e.target.value; }
  });

  render();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
