#!/usr/bin/env python3
"""agent-kit conflict review page, launched by scripts/install.sh.

Reads the install plan (plan.tsv), serves a page on 127.0.0.1 where the user compares
versions and resolves each item git-style (accept left / accept right / merge block by
block), then writes decisions.tsv and exits. Merge results are written into the user's
profile (overrides/), together with a .base file holding the hash of the generated
version they were merged against.

Exit code: 0 = applied, 1 = cancelled or timed out.
"""

import argparse
import difflib
import html
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_common  # noqa: E402

MAX_READ = 512 * 1024
MAX_WRITE = 1024 * 1024
FIELDS = ["id", "kind", "tool", "name", "src", "dest", "status", "left", "right", "target", "base"]


def read_text(path, msg):
    if not path or path == "-":
        return None
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_READ + 1)
    except OSError:
        return None
    text = data[:MAX_READ].decode("utf-8", errors="replace")
    if len(data) > MAX_READ:
        text += "\n" + msg.get("file_too_big", "…")
    return text


def list_files(root):
    out = set()
    if not os.path.isdir(root):
        return out
    for base, dirs, files in os.walk(root, followlinks=True):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("."):
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


def file_info(path, msg):
    try:
        st = os.stat(path)
    except OSError:
        return ""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
    if os.path.isdir(path):
        return msg.get("folder_info", "folder · modified %s").replace("%s", stamp)
    size = st.st_size
    size_text = "%d B" % size if size < 1024 else "%.1f KB" % (size / 1024.0)
    return msg.get("file_info", "%s · modified %s").replace("%s", size_text, 1).replace("%s", stamp, 1)


def mark_pair(a, b):
    """Character-level comparison of two similar lines; returns both sides as HTML with <mark>."""
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
    """Split two texts into identical sections and difference blocks, like git conflict hunks.

    Each item is either
      {"t": "eq", "a": left start line, "b": right start line, "lines": [...]}
    or
      {"t": "ch", "a": ..., "b": ..., "left": [...], "right": [...], "lh": [...], "rh": [...]}
    where lh/rh are escaped HTML with in-line highlights.
    """
    a = old.splitlines()
    b = new.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append({"t": "eq", "a": i1 + 1, "b": j1 + 1, "lines": a[i1:i2]})
            continue
        if out and out[-1]["t"] == "ch":
            out[-1]["left"].extend(a[i1:i2])
            out[-1]["right"].extend(b[j1:j2])
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
    return {"hunks": len(hunks), "removed": sum(len(s["left"]) for s in hunks), "added": sum(len(s["right"]) for s in hunks)}


class Review(ui_common.App):
    def __init__(self, args):
        super(Review, self).__init__()
        self.args = args
        self.home = args.home
        self.lang = args.lang
        self.msg = ui_common.load_messages(args.kit, args.lang)
        self.overrides = os.path.abspath(args.overrides)
        self.items = self.load_plan()

    def pretty(self, path):
        return ui_common.pretty(path, self.home)

    def load_plan(self):
        items = []
        with open(self.args.plan, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == len(FIELDS):
                    items.append(dict(zip(FIELDS, parts)))
        for item in items:
            self.enrich(item)
        return items

    def enrich(self, item):
        msg = self.msg
        item["dest_pretty"] = self.pretty(item["dest"])
        item["dest_info"] = file_info(item["dest"], msg)
        item["status_label"] = msg.get("chip_" + item["status"], item["status"])
        if item["status"] == "foreign":
            text = read_text(item["left"], msg)
            item["description"] = description_of(text or "")
            item["content"] = text if text is not None else msg.get("unreadable_short", "")
            return
        if item["status"] not in ("conflict", "outdated"):
            return
        old = read_text(item["left"], msg)
        new = read_text(item["right"], msg) or ""
        item["can_merge"] = item["target"] != "-" and old is not None
        item["target_pretty"] = self.pretty(item["target"]) if item["target"] != "-" else ""
        item["right_pretty"] = self.pretty(item["right"])
        item["left_pretty"] = self.pretty(item["left"]) if item["left"] != "-" else ""
        item["old_text"] = old if old is not None else ""
        item["new_text"] = new
        item["old_readable"] = old is not None
        if old is not None:
            item["segments"] = segments(old, new)
            item["stats"] = diff_stats(item["segments"])
        else:
            item["segments"] = []
            item["stats"] = None
        notes = []
        if item["kind"] == "skill" and item["status"] == "conflict":
            d, s = item["dest"], item["src"]
            if os.path.isdir(d) and os.path.isdir(s):
                a, b = list_files(d), list_files(s)
                if sorted(a - b):
                    notes.append(msg.get("only_old", "%s").replace("%s", ", ".join(sorted(a - b))))
                if sorted(b - a):
                    notes.append(msg.get("only_new", "%s").replace("%s", ", ".join(sorted(b - a))))
                notes.append(msg.get("skill_folder_note", ""))
        item["notes"] = notes

    def page(self):
        public = []
        for i in self.items:
            keep = dict(i)
            for k in ("src", "dest", "left", "right", "target", "base"):
                keep.pop(k, None)
            public.append(keep)
        return ui_common.page_shell(
            self.lang, self.msg.get("title_review", "agent-kit"), PAGE_CSS,
            {"items": public, "token": self.token, "messages": self.msg},
            ui_common.BASE_JS + PAGE_JS,
        )

    def handle(self, path, payload):
        if path != "/apply":
            return False, {"error": "not found"}, False
        error = self.apply(payload)
        if error:
            return False, {"error": error}, False
        return True, {"ok": True}, True

    def apply(self, payload):
        msg = self.msg
        decisions = payload.get("decisions") or {}
        merges = payload.get("merges") or {}
        by_id = dict((i["id"], i) for i in self.items)
        allowed = {
            "conflict": ("keep", "replace", "merge"),
            "outdated": ("keep", "replace", "merge"),
            "foreign": ("keep", "disable"),
        }
        lines = []
        writes = {}
        for item_id, action in decisions.items():
            item = by_id.get(str(item_id))
            if not item or item["status"] not in allowed:
                return msg.get("srv_bad_id", "invalid item: %s").replace("%s", str(item_id))
            if action not in allowed[item["status"]]:
                return msg.get("srv_bad_action", "invalid action: %s").replace("%s", str(action))
            if action == "merge":
                if not item.get("can_merge"):
                    return msg.get("srv_bad_action", "invalid action: %s").replace("%s", "merge")
                content = merges.get(str(item_id))
                if not isinstance(content, str) or not content.strip():
                    return msg.get("srv_empty_merge", "%s").replace("%s", item["name"])
                if len(content.encode("utf-8")) > MAX_WRITE:
                    return msg.get("srv_too_big", "%s").replace("%s", item["name"])
                target = os.path.normpath(os.path.abspath(item["target"]))
                if not target.startswith(self.overrides + os.sep):
                    return msg.get("srv_bad_target", "refused")
                previous = writes.get(target)
                if previous is not None and previous[0] != content:
                    return msg.get("srv_shared", "%s").replace("%s", item["name"])
                writes[target] = (content, item["base"])
            lines.append("%s\t%s\n" % (item_id, action))
        for target, (content, base) in writes.items():
            if not content.endswith("\n"):
                content += "\n"
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".tmp-agent-kit"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, target)
            with open(target + ".base", "w", encoding="utf-8") as f:
                f.write(base + "\n")
        with open(self.args.decisions, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return None


PAGE_CSS = r"""
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.chip { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 3px 12px; font-size: 13px; color: var(--muted); }
.chip b { color: var(--ink); font-weight: 600; margin-left: 4px; }
.chip.hot { border-color: var(--warn); color: var(--warn); background: var(--warn-bg); }
.chip.hot b { color: var(--warn); }
.legend-box { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: var(--muted); margin: -8px 0 22px; }
.legend-box .sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 6px; }
.sw.l { background: var(--left-bg); border: 1px solid var(--left); }
.sw.r { background: var(--right-bg); border: 1px solid var(--right); }
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
.tag.profile { border-color: var(--accent); color: var(--accent); }
.stat { font-size: 13px; white-space: nowrap; }
.stat .minus { color: var(--left); } .stat .plus { color: var(--right); }
.badge { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; white-space: nowrap; border: 1px solid transparent; }
.badge.todo { color: var(--warn); background: var(--warn-bg); border-color: var(--warn); }
.badge.ok { color: var(--ok); background: var(--ok-bg); }
.badge.doing { color: var(--accent); background: var(--accent-soft); }
.ops { display: flex; flex-wrap: wrap; gap: 6px; }
.op { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 7px; padding: 5px 10px; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
.op:hover:not(:disabled) { border-color: var(--accent); }
.op[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.op.l[aria-pressed="true"] { background: var(--left); border-color: var(--left); color: #fff; }
.op.r[aria-pressed="true"] { background: var(--right); border-color: var(--right); color: #fff; }
.op:disabled { opacity: .45; cursor: not-allowed; }
.op.ghost { border-color: transparent; background: transparent; color: var(--accent); padding-left: 4px; padding-right: 4px; }
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
.colrow { display: grid; grid-template-columns: 1fr 1fr; }
.colhead { padding: 8px 12px; font-size: 12px; font-weight: 600; border-bottom: 1px solid var(--line); word-break: break-all; }
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
textarea { width: 100%; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; line-height: 1.55; padding: 10px; }
.custom textarea { min-height: 120px; }
.custom .ops { margin-top: 8px; }
.result { margin-top: 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); overflow: hidden; }
.result summary { cursor: pointer; padding: 10px 12px; font-size: 13px; font-weight: 600; background: var(--code-bg); border-bottom: 1px solid var(--line); }
.result summary span { font-weight: 400; color: var(--muted); }
.result .rbody { max-height: 420px; overflow: auto; padding: 6px 0; }
.result .ln.mk .tx { background: var(--marker-bg); color: var(--warn); font-weight: 600; }
.result textarea { border: 0; border-radius: 0; min-height: 360px; }
.result .rfoot { padding: 8px 12px; border-top: 1px solid var(--line); font-size: 12.5px; color: var(--muted); }
.hint { font-size: 13px; color: var(--muted); margin: 0 0 12px; }
.hint.warn { color: var(--warn); }
pre.content { margin: 0; padding: 12px 14px; max-height: 320px; overflow: auto; white-space: pre-wrap; word-break: break-all; font-size: 12.5px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
details.rest { padding: 14px 20px; }
details.rest summary { cursor: pointer; color: var(--muted); font-size: 14px; }
details.rest ul { margin: 10px 0 0; padding-left: 18px; font-size: 13px; color: var(--muted); columns: 2; }
.empty { padding: 18px 20px; color: var(--muted); font-size: 14px; }
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
"""

PAGE_JS = r"""
(function () {
  "use strict";
  var items = DATA.items;
  var conflicts = items.filter(function (i) { return i.status === "conflict" || i.status === "outdated"; });
  var foreign = items.filter(function (i) { return i.status === "foreign"; });
  var rest = items.filter(function (i) { return ["conflict", "outdated", "foreign"].indexOf(i.status) < 0; });
  var byId = {};
  items.forEach(function (i) { byId[i.id] = i; });

  // per conflict: mode = null | left | right | merge; hunks[k].res = null | left | right | lr | rl | none | custom
  var S = {};
  conflicts.forEach(function (i) {
    var hunks = [];
    i.segments.forEach(function (sg) { if (sg.t === "ch") { sg.h = hunks.length; hunks.push({ res: null, custom: "", editing: false, draft: "" }); } });
    S[i.id] = { mode: null, open: false, hunks: hunks, manual: false, manualText: "", fold: {}, cur: -1 };
  });
  var F = {};
  foreign.forEach(function (i) { F[i.id] = { act: "keep", show: false }; });
  var confirmMarkers = false;

  function toolName(i) { return i.tool === "claude" ? "Claude Code" : i.tool === "codex" ? "Codex" : (MSG.tool_profile || "profile"); }
  function toolLabel(i) { return esc(toolName(i)); }
  function kindLabel(i) { return i.kind === "rules" ? T("kind_rules") : i.kind === "agent" ? T("kind_agent") : T("kind_skill"); }
  // conflict markers and headings use the plain (unescaped) labels
  function plainLeft(i) { return MSG[i.status === "outdated" ? "label_override" : "label_yours"] || "left"; }
  function plainRight(i) { return MSG[i.status === "outdated" ? "label_new" : "label_kit"] || "right"; }

  // ---- merge computation ----
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
  function composeLines(i, withMarkers) {
    var st = S[i.id], out = [];
    i.segments.forEach(function (sg) {
      if (sg.t === "eq") { sg.lines.forEach(function (x) { out.push({ t: x }); }); return; }
      var lines = hunkLines(sg, st.hunks[sg.h]);
      if (lines) { lines.forEach(function (x) { out.push({ t: x }); }); return; }
      if (!withMarkers) return;
      out.push({ t: "<<<<<<< " + plainLeft(i), mk: true });
      sg.left.forEach(function (x) { out.push({ t: x }); });
      out.push({ t: "=======", mk: true });
      sg.right.forEach(function (x) { out.push({ t: x }); });
      out.push({ t: ">>>>>>> " + plainRight(i), mk: true });
    });
    return out;
  }
  function composedText(i) { return composeLines(i, false).map(function (x) { return x.t; }).join("\n") + "\n"; }
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
    var st = S[i.id], od = i.status === "outdated";
    if (st.mode === "left") return '<span class="badge ok">' + T(od ? "st_left_override" : "st_left") + "</span>";
    if (st.mode === "right") return '<span class="badge ok">' + T(od ? "st_right_override" : "st_right") + "</span>";
    if (st.mode === "merge") {
      if (st.manual) return '<span class="badge ok">' + T("st_manual") + "</span>";
      var d = doneHunks(i), n = st.hunks.length;
      return d === n ? '<span class="badge ok">' + T("st_merged") + "</span>" : '<span class="badge doing">' + T("st_merging", d, n) + "</span>";
    }
    return '<span class="badge todo">' + T("st_todo") + "</span>";
  }

  // ---- conflict table ----
  function conflictRow(i) {
    var st = S[i.id], s = i.stats, od = i.status === "outdated";
    var stat = s ? '<span class="stat"><span class="minus">−' + s.removed + '</span> <span class="plus">+' + s.added +
      '</span><br><span class="meta">' + T("diff_count", s.hunks) + "</span></span>" : '<span class="meta">' + T("cannot_compare") + "</span>";
    var ops = '<div class="ops">' +
      '<button type="button" class="op l" data-mode="left" data-id="' + i.id + '" aria-pressed="' + (st.mode === "left") + '" title="' + T(od ? "op_left_t_override" : "op_left_t") + '">' + T("op_left") + "</button>" +
      '<button type="button" class="op r" data-mode="right" data-id="' + i.id + '" aria-pressed="' + (st.mode === "right") + '" title="' + T(od ? "op_right_t_override" : "op_right_t") + '">' + T("op_right") + "</button>" +
      '<button type="button" class="op" data-mode="merge" data-id="' + i.id + '" aria-pressed="' + (st.mode === "merge") + '"' +
      (i.can_merge ? "" : " disabled") + ' title="' + T(i.can_merge ? "op_merge_t" : "op_merge_disabled_t") + '">' + T("op_merge") + "</button>" +
      '<button type="button" class="op ghost" data-open="' + i.id + '">' + (st.open ? T("op_collapse") : (st.mode === "merge" ? T("op_continue") : T("op_view"))) + "</button></div>";
    var where = '<div class="path">' + esc(i.dest_pretty) + "</div>" + (od ? "" : '<div class="meta">' + esc(i.dest_info) + "</div>");
    var row = '<tr class="' + (st.open ? "row-open" : "") + '" id="row-' + i.id + '">' +
      '<td><span class="tag' + (od ? " profile" : "") + '">' + toolLabel(i) + "</span></td>" +
      '<td><div class="name">' + esc(i.name) + '</div><div class="meta">' + kindLabel(i) + (od ? " · " + T("chip_outdated") : "") + "</div></td>" +
      "<td>" + where + "</td><td>" + stat + "</td><td>" + statusBadge(i) + "</td><td>" + ops + "</td></tr>";
    if (!st.open) return row;
    return row + '<tr class="detail"><td colspan="6">' + mergePanel(i) + "</td></tr>";
  }

  function lineHTML(no, h, cls) {
    return '<div class="ln' + (cls ? " " + cls : "") + '"><span class="no">' + (no == null ? "" : no) + '</span><span class="tx">' + h + "</span></div>";
  }
  function sideLines(lines, start) {
    if (!lines.length) return '<div class="empty-side">' + T("side_empty") + "</div>";
    return lines.map(function (x, k) { return lineHTML(start + k, x); }).join("");
  }

  function mergePanel(i) {
    var st = S[i.id], merging = st.mode === "merge";
    var h = '<div class="panel">';
    if (i.status === "outdated") h += '<p class="hint">' + T("outdated_hint") + "</p>";
    if (i.notes && i.notes.length) h += '<div class="notes">' + i.notes.map(function (n) { return "<div>" + esc(n) + "</div>"; }).join("") + "</div>";
    if (!i.old_readable) return h + '<p class="hint warn">' + T("unreadable") + "</p></div>";
    if (!merging) h += '<p class="hint">' + T(i.can_merge ? "view_hint" : "view_hint_nomerge") + "</p>";
    if (merging) h += toolbar(i);
    if (merging && st.manual) h += '<p class="hint">' + T("manual_hint") + "</p>";
    h += '<div class="cols"><div class="colrow"><div class="colhead l">' + T("left_head", plainLeft(i), i.left_pretty || i.dest_pretty) +
      '</div><div class="colhead r">' + T("right_head", plainRight(i), i.right_pretty) + "</div></div>";
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
    var h = '<div class="toolbar"><div class="progress"><span>' + TH("progress", d, n) + '</span><span class="bar"><i style="width:' + pct + '%"></i></span></div>' +
      '<button type="button" class="op" data-nav="prev" data-id="' + i.id + '"' + dis + ">" + T("prev") + "</button>" +
      '<button type="button" class="op" data-nav="next" data-id="' + i.id + '"' + dis + ">" + T("next") + "</button>" +
      '<span class="sep"></span>' +
      '<button type="button" class="op l" data-all="left" data-id="' + i.id + '"' + dis + ">" + T("all_left") + "</button>" +
      '<button type="button" class="op r" data-all="right" data-id="' + i.id + '"' + dis + ">" + T("all_right") + "</button>" +
      '<button type="button" class="op" data-reset="' + i.id + '"' + dis + ">" + T("reset") + "</button>" +
      '<span class="sep"></span>' +
      '<button type="button" class="op" data-manual="' + i.id + '" aria-pressed="' + st.manual + '">' + T(st.manual ? "manual_off" : "manual_on") + "</button>";
    // items that write the same override file can reuse each other's result
    conflicts.forEach(function (o) {
      if (o.id !== i.id && o.target_pretty && o.target_pretty === i.target_pretty && S[o.id].mode === "merge" && isResolved(o)) {
        h += '<button type="button" class="op" data-copy-from="' + o.id + '" data-id="' + i.id + '">' + T("copy_from", toolName(o)) + "</button>";
      }
    });
    return h + "</div>";
  }

  function eqBlock(i, sg, k) {
    var st = S[i.id], lines = sg.lines;
    function both(from, to) {
      var l = "", r = "";
      for (var x = from; x < to; x++) { l += lineHTML(sg.a + x, esc(lines[x])); r += lineHTML(sg.b + x, esc(lines[x])); }
      return '<div class="seg eq"><div class="side">' + l + '</div><div class="side">' + r + "</div></div>";
    }
    if (lines.length <= 8 || st.fold[k]) return both(0, lines.length);
    return both(0, 3) + '<div class="fold"><button type="button" data-fold="' + k + '" data-id="' + i.id + '">' + T("unchanged_fold", lines.length - 6) + "</button></div>" + both(lines.length - 3, lines.length);
  }

  function hunkBlock(i, sg, n, total, active) {
    var st = S[i.id], hk = st.hunks[sg.h], res = hk.res;
    var lc = "side l", rc = "side r";
    if (res === "left") { lc += " pick"; rc += " dim"; }
    if (res === "right") { rc += " pick"; lc += " dim"; }
    if (res === "lr" || res === "rl") { lc += " pick"; rc += " pick"; }
    if (res === "none" || res === "custom") { lc += " dim"; rc += " dim"; }
    var cls = "hunk" + (res === null && active ? " todo" : "") + (st.cur === sg.h ? " cur" : "");
    var badge = st.mode === "merge" && st.manual ? '<span class="badge doing">' + T("hunk_by_manual") + "</span>" :
      res === null ? '<span class="badge todo">' + T("st_todo") + "</span>" : '<span class="badge ok">' + T("res_" + res) + "</span>";
    var h = '<div class="' + cls + '" id="hunk-' + i.id + "-" + sg.h + '"><div class="hhead"><span class="htitle">' + T("hunk_title", n, total) + "</span>" + badge;
    if (active) {
      var b = function (r, extra) {
        return '<button type="button" class="op' + (extra || "") + '" data-res="' + r + '" data-id="' + i.id + '" data-h="' + sg.h + '" aria-pressed="' + (res === r) + '" title="' + T("h_" + r + "_t") + '">' + T("h_" + r) + "</button>";
      };
      h += '<div class="ops">' + b("left", " l") + b("right", " r") + b("lr") + b("rl") + b("none") +
        '<button type="button" class="op" data-edit="' + sg.h + '" data-id="' + i.id + '" aria-pressed="' + (res === "custom") + '" title="' + T("h_edit_t") + '">' + T("h_edit") + "</button>" +
        (res !== null ? '<button type="button" class="op ghost" data-res="clear" data-id="' + i.id + '" data-h="' + sg.h + '">' + T("h_undo") + "</button>" : "") + "</div>";
    }
    h += '</div><div class="hbody"><div class="' + lc + '">' + sideLines(sg.lh, sg.a) + '</div><div class="' + rc + '">' + sideLines(sg.rh, sg.b) + "</div></div>";
    if (res === "lr") h += '<div class="order">' + T("order_lr") + "</div>";
    if (res === "rl") h += '<div class="order">' + T("order_rl") + "</div>";
    if (hk.editing) {
      h += '<div class="custom"><label for="ed-' + i.id + "-" + sg.h + '">' + T("edit_label") + "</label>" +
        '<textarea id="ed-' + i.id + "-" + sg.h + '" data-edit-text="' + sg.h + '" data-id="' + i.id + '">' + esc(hk.draft) + "</textarea>" +
        '<div class="ops"><button type="button" class="op" aria-pressed="true" data-edit-ok="' + sg.h + '" data-id="' + i.id + '">' + T("done") + "</button>" +
        '<button type="button" class="op" data-edit-cancel="' + sg.h + '" data-id="' + i.id + '">' + T("cancel") + "</button></div></div>";
    } else if (res === "custom") {
      h += '<div class="custom"><label>' + T("custom_label") + '</label><pre class="content">' + (hk.custom ? esc(hk.custom) : T("empty")) + "</pre></div>";
    }
    return h + "</div>";
  }

  function resultBox(i) {
    var st = S[i.id];
    var h = '<details class="result" open><summary>' + T("result_title") + " <span>· " + T("result_where", i.target_pretty, i.dest_pretty) + "</span></summary>";
    if (st.manual) h += '<textarea id="man-' + i.id + '" data-manual-text="' + i.id + '">' + esc(st.manualText) + "</textarea>";
    else h += '<div class="rbody" id="pv-' + i.id + '">' + composeLines(i, true).map(function (x, k) { return lineHTML(k + 1, esc(x.t), x.mk ? "mk" : ""); }).join("") + "</div>";
    h += '<div class="rfoot">' + T(st.manual ? "result_foot_manual" : "result_foot_markers") + " " + T("result_foot_sync") + "</div></details>";
    return h;
  }

  // ---- other-source skills ----
  function foreignRow(i) {
    var f = F[i.id];
    var row = '<tr class="' + (f.show ? "row-open" : "") + '"><td><span class="tag">' + toolLabel(i) + "</span></td>" +
      '<td><div class="name">' + esc(i.name) + '</div><div class="desc">' + (i.description ? esc(i.description) : T("no_desc")) + "</div></td>" +
      '<td><div class="path">' + esc(i.dest_pretty) + '</div><div class="meta">' + esc(i.dest_info) + "</div></td>" +
      "<td>" + (f.act === "disable" ? '<span class="badge doing">' + T("will_disable") + "</span>" : '<span class="badge ok">' + T("keep") + "</span>") + "</td>" +
      '<td><div class="ops"><button type="button" class="op" data-fact="keep" data-id="' + i.id + '" aria-pressed="' + (f.act === "keep") + '">' + T("keep") + "</button>" +
      '<button type="button" class="op" data-fact="disable" data-id="' + i.id + '" aria-pressed="' + (f.act === "disable") + '" title="' + T("disable_t") + '">' + T("disable") + "</button>" +
      '<button type="button" class="op ghost" data-fshow="' + i.id + '">' + (f.show ? T("op_collapse") : T("view_content")) + "</button></div></td></tr>";
    if (!f.show) return row;
    return row + '<tr class="detail"><td colspan="5"><div class="panel"><pre class="content">' + esc(i.content) + "</pre></div></td></tr>";
  }

  function count(st) { return rest.filter(function (i) { return i.status === st; }).length; }

  function render() {
    var y = window.scrollY;
    var resolved = conflicts.filter(isResolved).length;
    var h = '<div class="topbar"><div><h1>' + T("review_title") + '</h1><p class="lead">' + TH("review_lead") + "</p></div>" +
      '<button type="button" class="btn" id="theme">' + T("theme") + "</button></div>";
    h += '<div class="chips"><span class="chip' + (resolved < conflicts.length ? " hot" : "") + '">' + T("chip_resolved") + "<b>" + resolved + " / " + conflicts.length + "</b></span>" +
      '<span class="chip">' + T("chip_foreign") + "<b>" + foreign.length + "</b></span>" +
      '<span class="chip">' + T("chip_new") + "<b>" + count("new") + "</b></span>" +
      '<span class="chip">' + T("chip_update") + "<b>" + count("update") + "</b></span>" +
      '<span class="chip">' + T("chip_uptodate") + "<b>" + count("uptodate") + "</b></span></div>";
    h += '<div class="legend-box"><span><span class="sw l"></span>' + T("legend_left") + '</span><span><span class="sw r"></span>' + T("legend_right") + "</span><span>" + T("legend_mark") + "</span></div>";

    h += '<section><div class="sec-head"><h2>' + T("sec_conflicts", conflicts.length) + "</h2><p>" + T("sec_conflicts_hint") + "</p></div>";
    if (conflicts.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>' + T("col_tool") + "</th><th>" + T("col_name") + "</th><th>" + T("col_location") +
        "</th><th>" + T("col_diff") + "</th><th>" + T("col_status") + "</th><th>" + T("col_actions") + "</th></tr></thead><tbody>" +
        conflicts.map(conflictRow).join("") + "</tbody></table></div>";
    } else h += '<div class="empty">' + T("none_conflicts") + "</div>";
    h += "</section>";

    h += '<section><div class="sec-head"><h2>' + T("sec_foreign", foreign.length) + "</h2><p>" + T("sec_foreign_hint") + "</p></div>";
    if (foreign.length) {
      h += '<div class="table-wrap"><table class="list"><thead><tr><th>' + T("col_tool") + "</th><th>" + T("col_name_desc") + "</th><th>" + T("col_location") +
        "</th><th>" + T("col_status") + "</th><th>" + T("col_actions") + "</th></tr></thead><tbody>" + foreign.map(foreignRow).join("") + "</tbody></table></div>";
    } else h += '<div class="empty">' + T("none_foreign") + "</div>";
    h += "</section>";

    h += '<section><details class="rest"><summary>' + T("rest", rest.length) + "</summary><ul>" +
      rest.map(function (i) { return "<li>" + toolLabel(i) + " · " + esc(i.name) + " · " + esc(i.status_label) + "</li>"; }).join("") + "</ul></details></section>";

    document.getElementById("app").innerHTML = h;
    renderFooter();
    window.scrollTo(0, y);
  }

  function renderFooter(error) {
    var resolved = conflicts.filter(isResolved).length, left = conflicts.length - resolved;
    var c = { left: 0, right: 0, merge: 0 };
    conflicts.forEach(function (i) { if (S[i.id].mode && isResolved(i)) c[S[i.id].mode]++; });
    var dis = foreign.filter(function (i) { return F[i.id].act === "disable"; }).length;
    var detail = [];
    if (c.left) detail.push(T("foot_left_count", c.left));
    if (c.right) detail.push(T("foot_right_count", c.right));
    if (c.merge) detail.push(T("foot_merge_count", c.merge));
    if (foreign.length) detail.push(T("foot_disable_count", dis));
    document.getElementById("footer").innerHTML = '<div class="foot"><div class="sum">' +
      (conflicts.length ? T("foot_resolved", resolved, conflicts.length) : T("foot_none")) +
      "<small>" + (detail.join(" · ") || T("foot_hint")) + (left ? " · " + T("foot_left", left) : "") + "</small></div>" +
      (left ? '<button type="button" class="btn" id="keep-rest" title="' + T("keep_rest_t") + '">' + T("keep_rest") + "</button>" : "") +
      '<button type="button" class="btn" id="cancel">' + T("cancel") + "</button>" +
      '<button type="button" class="btn primary" id="apply"' + (left ? " disabled" : "") + ">" + T("apply") + "</button>" +
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

  function fill(key, a, b) { return (MSG[key] || key).replace("%s", a).replace("%s", b); }

  function buildPayload() {
    var decisions = {}, merges = {}, byTarget = {};
    for (var k = 0; k < conflicts.length; k++) {
      var i = conflicts[k], st = S[i.id];
      if (st.mode === "left") decisions[i.id] = "keep";
      else if (st.mode === "right") decisions[i.id] = "replace";
      else {
        var text = finalText(i);
        if (norm(text) === norm(i.new_text)) { decisions[i.id] = "replace"; continue; }
        if (i.status === "outdated" && norm(text) === norm(i.old_text)) { decisions[i.id] = "keep"; continue; }
        decisions[i.id] = "merge";
        merges[i.id] = text;
        var who = toolName(i) + " · " + i.name, prev = byTarget[i.target_pretty];
        if (prev && norm(prev.text) !== norm(text)) return { error: fill("err_shared", prev.who, who) };
        byTarget[i.target_pretty] = { text: text, who: who };
      }
    }
    foreign.forEach(function (i) { decisions[i.id] = F[i.id].act; });
    return { decisions: decisions, merges: merges };
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (!t || t.disabled) return;
    var d = t.dataset, i = d.id ? byId[d.id] : null, st = i ? S[i.id] : null;
    if (d.mode) { st.mode = st.mode === d.mode ? null : d.mode; if (st.mode === "merge") st.open = true; return render(); }
    if (d.open) { S[d.open].open = !S[d.open].open; return render(); }
    if (d.res) {
      var hk = st.hunks[+d.h];
      hk.res = d.res === "clear" ? null : d.res;
      hk.editing = false;
      st.cur = +d.h;
      render();
      if (d.res !== "clear") {
        var nx = nextTodo(i, 1);
        if (nx >= 0 && nx !== +d.h) scrollToHunk(i, nx);
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
    if (d.nav) { var k = nextTodo(i, d.nav === "next" ? 1 : -1); if (k >= 0) scrollToHunk(i, k); return; }
    if (d.all) { st.hunks.forEach(function (h) { if (h.res === null) h.res = d.all; }); return render(); }
    if (d.reset) { S[d.reset].hunks.forEach(function (h) { h.res = null; h.editing = false; }); S[d.reset].cur = -1; return render(); }
    if (d.manual) {
      var m = S[d.manual];
      if (m.manual) { m.manual = false; return render(); }
      m.manualText = composeLines(byId[d.manual], true).map(function (x) { return x.t; }).join("\n") + "\n";
      m.manual = true;
      return render();
    }
    if (d.copyFrom) { st.manualText = finalText(byId[d.copyFrom]); st.manual = true; return render(); }
    if (d.fold) { st.fold[d.fold] = true; return render(); }
    if (d.fact) { F[d.id].act = d.fact; return render(); }
    if (d.fshow) { F[d.fshow].show = !F[d.fshow].show; return render(); }
    if (t.id === "theme") return toggleTheme();
    if (t.id === "keep-rest") { conflicts.forEach(function (c) { if (!isResolved(c)) S[c.id].mode = "left"; }); return render(); }
    if (t.id === "cancel") { post("/cancel").then(function () { finish(T("cancelled_title"), T("cancelled_text")); }); return; }
    if (t.id === "apply") {
      var withMarkers = conflicts.filter(function (c) { return S[c.id].mode === "merge" && S[c.id].manual && /^(<{7}|={7}|>{7})( |$)/m.test(S[c.id].manualText); });
      if (withMarkers.length && !confirmMarkers) { confirmMarkers = true; return renderFooter(fill("err_markers", withMarkers[0].name)); }
      var p = buildPayload();
      if (p.error) return renderFooter(p.error);
      t.disabled = true;
      post("/apply", p).then(function (r) {
        if (r.ok) finish(T("finished_title"), T("finished_text"));
        else renderFooter(r.body.error || MSG.err_submit);
      }).catch(function () { renderFooter(MSG.err_conn); });
    }
  });
  document.addEventListener("input", function (e) {
    var d = e.target.dataset;
    confirmMarkers = false;
    if (d.editText !== undefined && d.editText !== "") S[d.id].hunks[+d.editText].draft = e.target.value;
    if (d.manualText) S[d.manualText].manualText = e.target.value;
  });
  render();
})();
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--decisions", required=True)
    p.add_argument("--kit", required=True)
    p.add_argument("--home", default=os.path.expanduser("~"))
    p.add_argument("--overrides", required=True)
    p.add_argument("--lang", default="en")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args()
    app = Review(args)
    return ui_common.serve(app, app.msg, no_open=args.no_open, port=args.port)


if __name__ == "__main__":
    sys.exit(main())
