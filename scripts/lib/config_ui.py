#!/usr/bin/env python3
"""agent-kit settings form, launched by `scripts/configure.sh --web`.

Shows every setting with a live preview of the global rules they generate. Saving writes
the same files as the terminal questionnaire (through save-settings.sh): profile.sh in the
profile folder, machine.sh for this computer, and rules/custom.md for extra rules.

Exit code: 0 = saved, 1 = cancelled or timed out.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_common  # noqa: E402

SAFE = re.compile(r'^[^"`\\$]*$')
PROFILE_KEYS = ["UI_LANG", "CONTENT_LANG", "REPLY_LANG", "DOCS_LANG", "WORK_MODE", "DESIGN",
                "PLANNING", "COMMITS", "SCAFFOLD", "STACKS", "SKILLS", "TOOLS"]
LANGS = ["en", "zh-CN"]


def parse_options(kit):
    out = {}
    with open(os.path.join(kit, "scripts", "lib", "options.sh"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(OPT_[A-Z_]+)='(.*)'\s*$", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def skill_description(folder, lang):
    path = os.path.join(folder, "SKILL.%s.md" % lang)
    if not os.path.isfile(path):
        path = os.path.join(folder, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("description:"):
                    return line[len("description:"):].strip()
    except OSError:
        pass
    return ""


class Config(ui_common.App):
    def __init__(self, args):
        super(Config, self).__init__()
        self.args = args
        self.kit = args.kit
        self.home = args.home
        self.profile_dir = args.profile_dir
        self.opts = parse_options(self.kit)
        self.current = self.load_current()
        self.lang = self.current.get("UI_LANG", "en")
        self.msg = ui_common.load_messages(self.kit, self.lang)
        self.messages = dict((code, ui_common.load_messages(self.kit, code)) for code in LANGS)

    def bash(self, script, extra_env=None):
        env = dict(os.environ)
        env["HOME"] = self.home
        if extra_env:
            env.update(extra_env)
        return subprocess.run(["bash", "-c", script], cwd=self.kit, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def load_current(self):
        keys = " ".join(PROFILE_KEYS)
        script = (
            '. scripts/lib/common.sh; load_settings; '
            'for k in %s; do eval "printf \'%%s=%%s\\n\' \\"$k\\" \\"\\$$k\\""; done; '
            'printf "PROJECT_DIRS=%%s\\n" "$PROJECT_DIRS"; printf "MISSING=%%s\\n" "$MISSING_KEYS"' % keys
        )
        res = self.bash(script)
        out = {}
        for line in res.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
        custom = os.path.join(self.profile_dir, "rules", "custom.md")
        out["CUSTOM_RULES"] = open(custom, encoding="utf-8").read() if os.path.isfile(custom) else ""
        return out

    def repo_data(self):
        stacks = sorted(d for d in os.listdir(os.path.join(self.kit, "stacks"))
                        if os.path.isdir(os.path.join(self.kit, "stacks", d)))
        skills = []
        base = os.path.join(self.kit, "skills")
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if os.path.isfile(os.path.join(folder, "SKILL.md")):
                skills.append({"name": name, "stack": "", "desc": dict((l, skill_description(folder, l)) for l in LANGS)})
        for stack in stacks:
            sbase = os.path.join(self.kit, "stacks", stack, "skills")
            if not os.path.isdir(sbase):
                continue
            for name in sorted(os.listdir(sbase)):
                folder = os.path.join(sbase, name)
                if os.path.isfile(os.path.join(folder, "SKILL.md")):
                    skills.append({"name": name, "stack": stack, "desc": dict((l, skill_description(folder, l)) for l in LANGS)})
        return stacks, skills

    def page(self):
        stacks, skills = self.repo_data()
        cur = dict(self.current)
        dirs = [ui_common.pretty(d, self.home) for d in cur.get("PROJECT_DIRS", "").split(":") if d]
        data = {
            "token": self.token,
            "messages": self.msg,
            "allMessages": self.messages,
            "current": cur,
            "dirs": dirs,
            "options": self.opts,
            "stacks": stacks,
            "skills": skills,
            "paths": {
                "profile": ui_common.pretty(os.path.join(self.profile_dir, "profile.sh"), self.home),
                "machine": ui_common.pretty(self.args.machine, self.home),
                "custom": ui_common.pretty(os.path.join(self.profile_dir, "rules", "custom.md"), self.home),
            },
        }
        return ui_common.page_shell(self.lang, self.msg.get("cfg_title", "agent-kit settings"), PAGE_CSS, data,
                                    ui_common.BASE_JS + PAGE_JS)

    # ---- validation ----
    def validate(self, s):
        msg = self.msg
        o = self.opts

        def choice(key, value, allow_free=False):
            allowed = o.get("OPT_%s_CHOICES" % key, "").split()
            if value in allowed:
                return value
            if allow_free and "*" in allowed and value and SAFE.match(value) and len(value) <= 60:
                return value
            raise ValueError(msg.get("cfg_err_value", "%s").replace("%s", key))

        out = {}
        out["UI_LANG"] = choice("UI_LANG", s.get("UI_LANG", "en"))
        out["CONTENT_LANG"] = choice("CONTENT_LANG", s.get("CONTENT_LANG", "en"))
        out["REPLY_LANG"] = choice("REPLY_LANG", (s.get("REPLY_LANG") or "").strip(), True)
        out["DOCS_LANG"] = choice("DOCS_LANG", (s.get("DOCS_LANG") or "").strip(), True)
        for key in ("WORK_MODE", "DESIGN", "PLANNING", "COMMITS"):
            out[key] = choice(key, s.get(key, ""))
        scaffold = (s.get("SCAFFOLD") or "").strip()
        if not SAFE.match(scaffold) or len(scaffold) > 200:
            raise ValueError(msg.get("cfg_err_value", "%s").replace("%s", "SCAFFOLD"))
        out["SCAFFOLD"] = scaffold
        stacks, skills = self.repo_data()
        chosen = [x for x in (s.get("STACKS") or []) if x in stacks]
        out["STACKS"] = " ".join(chosen)
        tools = [x for x in (s.get("TOOLS") or []) if x in o.get("OPT_TOOLS_CHOICES", "").split()]
        if not tools:
            raise ValueError(msg.get("cfg_err_tools", "tools"))
        out["TOOLS"] = " ".join(tools)
        if s.get("SKILLS") == "all":
            out["SKILLS"] = "all"
        else:
            names = set(k["name"] for k in skills)
            picked = [x for x in (s.get("SKILLS") or []) if x in names]
            if not picked:
                raise ValueError(msg.get("cfg_err_skills", "skills"))
            out["SKILLS"] = " ".join(picked)
        dirs = []
        for raw in s.get("DIRS") or []:
            d = (raw or "").strip()
            if not d:
                continue
            if d == "~" or d.startswith("~/"):
                d = self.home + d[1:]
            d = d.rstrip("/") or "/"
            if not d.startswith("/") or re.search(r'[":`$\\]', d):
                raise ValueError(msg.get("cfg_err_dir", "%s").replace("%s", raw))
            if d == self.home:
                cfg = "$HOME"
            elif d.startswith(self.home + "/"):
                cfg = "$HOME" + d[len(self.home):]
            else:
                cfg = d
            if cfg not in dirs:
                dirs.append(cfg)
        out["PROJECT_DIRS"] = ":".join(dirs)
        rules = s.get("CUSTOM_RULES") or ""
        if len(rules.encode("utf-8")) > 256 * 1024:
            raise ValueError(msg.get("cfg_err_rules", "rules"))
        out["CUSTOM_RULES"] = rules
        return out

    def dir_status(self, cfg_dirs):
        out = []
        for d in [x for x in cfg_dirs.split(":") if x]:
            path = d.replace("$HOME", self.home)
            out.append({"path": ui_common.pretty(path, self.home), "exists": os.path.isdir(path)})
        return out

    # ---- endpoints ----
    def preview(self, v):
        tmp = tempfile.mkdtemp(prefix="agent-kit-preview-")
        try:
            prof = os.path.join(tmp, "profile.sh")
            with open(prof, "w", encoding="utf-8") as f:
                for k in PROFILE_KEYS:
                    f.write('%s="%s"\n' % (k, v[k]))
            rules_dir = os.path.join(tmp, "rules")
            os.makedirs(rules_dir)
            src_rules = os.path.join(self.profile_dir, "rules")
            if os.path.isdir(src_rules):
                for name in os.listdir(src_rules):
                    if name.endswith(".md") and name != "custom.md":
                        shutil.copy(os.path.join(src_rules, name), rules_dir)
            if v["CUSTOM_RULES"].strip():
                with open(os.path.join(rules_dir, "custom.md"), "w", encoding="utf-8") as f:
                    f.write(v["CUSTOM_RULES"])
            res = self.bash('bash scripts/build.sh --rules --profile "$AK_PREVIEW_PROFILE"',
                            {"AK_PREVIEW_PROFILE": prof, "AGENT_KIT_RULES_DIR": tmp})
            if res.returncode != 0:
                raise ValueError(res.stderr.strip() or "build failed")
            return res.stdout
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def save(self, v):
        env = dict(("AK_SET_" + k, v[k]) for k in PROFILE_KEYS)
        env["AK_SET_PROJECT_DIRS"] = v["PROJECT_DIRS"]
        res = self.bash("bash scripts/lib/save-settings.sh", env)
        if res.returncode != 0:
            raise ValueError(res.stderr.strip() or "save failed")
        custom = os.path.join(self.profile_dir, "rules", "custom.md")
        if v["CUSTOM_RULES"].strip():
            os.makedirs(os.path.dirname(custom), exist_ok=True)
            text = v["CUSTOM_RULES"]
            if not text.endswith("\n"):
                text += "\n"
            with open(custom, "w", encoding="utf-8") as f:
                f.write(text)
        elif os.path.isfile(custom):
            os.remove(custom)

    def browse(self, raw):
        """List the sub-folders of a folder, for the folder picker. Names only; no file contents."""
        path = os.path.expanduser((raw or "").strip() or self.home)
        path = os.path.realpath(path)
        while path != os.path.dirname(path) and not os.path.isdir(path):
            path = os.path.dirname(path)
        names, truncated = [], False
        try:
            entries = sorted(os.listdir(path), key=lambda n: n.lower())
        except OSError:
            entries = []
        for n in entries:
            if n.startswith("."):
                continue
            if os.path.isdir(os.path.join(path, n)):
                if len(names) >= 500:
                    truncated = True
                    break
                names.append(n)
        parent = os.path.dirname(path)
        return {
            "path": path,
            "shown": ui_common.pretty(path, self.home),
            "parent": parent if parent != path else "",
            "home": self.home,
            "dirs": names,
            "truncated": truncated,
        }

    def handle(self, path, payload):
        if path == "/browse":
            return True, self.browse(payload.get("path")), False
        try:
            v = self.validate(payload.get("settings") or {})
        except ValueError as exc:
            return False, {"error": str(exc)}, False
        if path == "/preview":
            try:
                text = self.preview(v)
            except ValueError as exc:
                return False, {"error": str(exc)}, False
            return True, {"text": text, "dirs": self.dir_status(v["PROJECT_DIRS"])}, False
        if path == "/save":
            try:
                self.save(v)
            except ValueError as exc:
                return False, {"error": str(exc)}, False
            return True, {"ok": True}, True
        return False, {"error": "not found"}, False


PAGE_CSS = r"""
.layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr); gap: 20px; }
.layout > .form { align-self: start; }
.form section { padding: 0; }
.field { padding: 14px 20px; border-top: 1px solid var(--line); }
.field:first-of-type { border-top: 0; }
.field > label, .field > .label { display: block; font-weight: 600; font-size: 14px; margin-bottom: 2px; }
.field .hint { font-size: 12.5px; color: var(--muted); margin: 0 0 8px; }
.choices { display: flex; flex-direction: column; gap: 6px; }
.choices.inline { flex-direction: row; flex-wrap: wrap; gap: 6px 16px; }
.choice { display: flex; gap: 8px; align-items: flex-start; font-size: 14px; cursor: pointer; }
.choice input { margin-top: 4px; }
.choice small { display: block; color: var(--muted); font-size: 12.5px; }
select, input[type=text] { padding: 7px 10px; font-size: 14px; width: 100%; max-width: 420px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.row select { width: auto; }
.dir { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.dir input { flex: 1; max-width: none; font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
.dir .warn { color: var(--warn); font-size: 12px; white-space: nowrap; }
.small { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 7px; padding: 5px 10px; font: inherit; font-size: 13px; cursor: pointer; }
.small.ghost { border-color: transparent; color: var(--accent); }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; padding: 16px; z-index: 50; }
.modal { background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 12px; width: min(560px, 100%); max-height: min(640px, 100%); display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,.25); }
.modal h3 { margin: 0; padding: 14px 18px 4px; font-size: 16px; }
.modal .bar { display: flex; gap: 8px; align-items: center; padding: 8px 18px; }
.modal .bar input { flex: 1; max-width: none; font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
.modal .list { flex: 1; overflow: auto; margin: 0 18px; border: 1px solid var(--line); border-radius: 8px; min-height: 160px; }
.modal .list button { display: block; width: 100%; text-align: left; border: 0; border-bottom: 1px solid var(--line); background: transparent; color: var(--ink); padding: 8px 12px; font: inherit; font-size: 14px; cursor: pointer; }
.modal .list button:last-child { border-bottom: 0; }
.modal .list button:hover, .modal .list button:focus-visible { background: color-mix(in srgb, var(--accent) 10%, transparent); outline: none; }
.modal .list .none { padding: 14px 12px; color: var(--muted); font-size: 13px; }
.modal .foot { display: flex; gap: 8px; justify-content: flex-end; align-items: center; padding: 12px 18px 16px; flex-wrap: wrap; }
.modal .foot .cur { flex: 1; min-width: 0; font-size: 12.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, Menlo, monospace; }
textarea.rules { width: 100%; min-height: 140px; padding: 10px; font-family: ui-monospace, Menlo, monospace; font-size: 13px; line-height: 1.5; resize: vertical; }
.skills { display: grid; grid-template-columns: 1fr; gap: 6px; margin-top: 8px; padding-left: 4px; }
.skills .choice code { font-size: 13px; }
.preview { position: sticky; top: 16px; }
.preview .sec-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.preview pre { margin: 0; padding: 14px 16px; max-height: calc(100vh - 220px); overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; line-height: 1.55; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.preview .state { font-size: 12px; color: var(--muted); }
.files { font-size: 12.5px; color: var(--muted); margin: -6px 0 18px; }
.files code { font-size: 12px; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .preview { position: static; }
  .preview pre { max-height: 420px; }
  main { padding: 20px 16px; }
}
"""

PAGE_JS = r"""
(function () {
  "use strict";
  var C = DATA.current, O = DATA.options;
  function list(s) { return (s || "").split(/\s+/).filter(Boolean); }
  var st = {
    UI_LANG: C.UI_LANG || "en", CONTENT_LANG: C.CONTENT_LANG || "en", REPLY_LANG: C.REPLY_LANG || "en", DOCS_LANG: C.DOCS_LANG || "reply",
    WORK_MODE: C.WORK_MODE, DESIGN: C.DESIGN, PLANNING: C.PLANNING, COMMITS: C.COMMITS, SCAFFOLD: C.SCAFFOLD || "",
    STACKS: list(C.STACKS), TOOLS: list(C.TOOLS), SKILLS: C.SKILLS === "all" || !C.SKILLS ? "all" : list(C.SKILLS),
    DIRS: DATA.dirs.length ? DATA.dirs.slice() : [""], CUSTOM_RULES: C.CUSTOM_RULES || ""
  };
  var dirState = [];
  var previewText = "", previewErr = "", timer = null, busy = false;

  function useLang(code) { MSG = DATA.allMessages[code] || MSG; document.documentElement.lang = code; }
  useLang(st.UI_LANG);

  function presets(key) { return list(O["OPT_" + key + "_CHOICES"]).filter(function (v) { return v !== "*"; }); }
  function optLabel(key, v) {
    var k = "opt_" + key + "_" + v.replace(/-/g, "_");
    if (MSG[k]) return T(k);
    var l = "lang_" + v.replace(/-/g, "_");
    return MSG[l] ? T(l) : esc(v);
  }

  function radios(key) {
    return '<div class="choices">' + presets(key).map(function (v) {
      return '<label class="choice"><input type="radio" name="' + key + '" value="' + esc(v) + '"' + (st[key] === v ? " checked" : "") + "><span>" + optLabel(key, v) + "</span></label>";
    }).join("") + "</div>";
  }
  function checks(key, values, labelFn, inline) {
    return '<div class="choices' + (inline ? " inline" : "") + '">' + values.map(function (v) {
      return '<label class="choice"><input type="checkbox" data-multi="' + key + '" value="' + esc(v) + '"' + (st[key].indexOf(v) >= 0 ? " checked" : "") + "><span>" + labelFn(v) + "</span></label>";
    }).join("") + "</div>";
  }
  // a language select with presets plus "other" (free text)
  function langSelect(key, withReply) {
    var vals = presets(key), isPreset = vals.indexOf(st[key]) >= 0;
    var h = '<div class="row"><select data-lang="' + key + '">' + vals.map(function (v) {
      return '<option value="' + esc(v) + '"' + (st[key] === v ? " selected" : "") + ">" + optLabel(key, v) + "</option>";
    }).join("") + '<option value="*"' + (isPreset ? "" : " selected") + ">" + T("cfg_other_lang") + "</option></select>";
    if (!isPreset) h += '<input type="text" data-free="' + key + '" value="' + esc(st[key]) + '" placeholder="' + T("cfg_other_lang_ph") + '">';
    return h + "</div>";
  }
  function field(label, hint, body) {
    return '<div class="field"><div class="label">' + label + "</div>" + (hint ? '<p class="hint">' + hint + "</p>" : "") + body + "</div>";
  }

  function render() {
    var y = window.scrollY;
    var h = '<div class="topbar"><div><h1>' + T("cfg_title") + '</h1><p class="lead">' + T("cfg_lead") + "</p></div>" +
      '<button type="button" class="btn" id="theme">' + T("theme") + "</button></div>";
    h += '<p class="files">' + T("cfg_files") + ' <code>' + esc(DATA.paths.profile) + "</code> · <code>" + esc(DATA.paths.machine) + "</code></p>";
    h += '<div class="layout"><div class="form">';

    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_language") + "</h2></div>" +
      field(T("cfg_ui_lang"), T("cfg_ui_lang_hint"), '<div class="row"><select id="ui-lang">' + ["en", "zh-CN"].map(function (v) {
        return '<option value="' + v + '"' + (st.UI_LANG === v ? " selected" : "") + ">" + optLabel("UI_LANG", v) + "</option>";
      }).join("") + "</select></div>") +
      field(T("q_content_lang"), T("q_content_lang_hint"), radios("CONTENT_LANG")) +
      field(T("q_reply_lang"), T("q_reply_lang_hint"), langSelect("REPLY_LANG")) +
      field(T("q_docs_lang"), T("q_docs_lang_hint"), langSelect("DOCS_LANG")) + "</section>";

    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_about") + "</h2></div>" +
      field(T("q_work_mode"), "", radios("WORK_MODE")) +
      field(T("q_design"), "", radios("DESIGN")) +
      field(T("q_scaffold"), T("cfg_scaffold_hint"), '<input type="text" id="scaffold" value="' + esc(st.SCAFFOLD) + '" placeholder="' + T("cfg_scaffold_ph") + '">') + "</section>";

    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_workflow") + "</h2></div>" +
      field(T("q_planning"), "", radios("PLANNING")) +
      field(T("q_commits"), "", radios("COMMITS")) + "</section>";

    var skillsBody = '<div class="choices"><label class="choice"><input type="radio" name="skills-mode" value="all"' + (st.SKILLS === "all" ? " checked" : "") + "><span>" + T("skills_all") + "</span></label>" +
      '<label class="choice"><input type="radio" name="skills-mode" value="pick"' + (st.SKILLS === "all" ? "" : " checked") + "><span>" + T("skills_pick") + "</span></label></div>";
    if (st.SKILLS !== "all") {
      skillsBody += '<div class="skills">' + DATA.skills.map(function (k) {
        var on = st.SKILLS.indexOf(k.name) >= 0, off = k.stack && st.STACKS.indexOf(k.stack) < 0;
        return '<label class="choice"><input type="checkbox" data-skill="' + esc(k.name) + '"' + (on ? " checked" : "") + "><span><code>" + esc(k.name) + "</code>" +
          (k.stack ? " · " + optLabel("STACKS", k.stack) : "") + (off ? " · " + T("cfg_stack_off") : "") +
          "<small>" + esc(((k.desc[st.UI_LANG] || k.desc.en || "").split(/\.\s|。/)[0] || "").slice(0, 160)) + "</small></span></label>";
      }).join("") + "</div>";
    }
    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_install") + "</h2></div>" +
      field(T("q_tools"), "", checks("TOOLS", list(O.OPT_TOOLS_CHOICES), function (v) { return optLabel("TOOLS", v); }, true)) +
      field(T("q_stacks"), T("cfg_stacks_hint"), checks("STACKS", DATA.stacks, function (v) { return optLabel("STACKS", v); }, true)) +
      field(T("q_skills"), T("q_skills_hint"), skillsBody) + "</section>";

    var dirs = st.DIRS.map(function (d, k) {
      var info = dirState.filter(function (x) { return x.path === d.replace(/\/+$/, ""); })[0];
      return '<div class="dir"><input type="text" data-dir="' + k + '" value="' + esc(d) + '" placeholder="~/Work/Projects">' +
        (info && !info.exists ? '<span class="warn">' + T("cfg_dir_missing") + "</span>" : "") +
        '<button type="button" class="small" data-choose="' + k + '">' + T("cfg_choose") + "</button>" +
        '<button type="button" class="small ghost" data-rmdir="' + k + '">' + T("cfg_remove") + "</button></div>";
    }).join("");
    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_machine") + "</h2><p>" + T("cfg_machine_hint") + "</p></div>" +
      field(T("cfg_dirs"), T("cfg_dirs_hint"), dirs + '<button type="button" class="small" id="add-dir">' + T("cfg_add_dir") + "</button>") + "</section>";

    h += '<section><div class="sec-head"><h2>' + T("cfg_sec_extra") + "</h2><p>" + T("cfg_extra_hint", DATA.paths.custom) + "</p></div>" +
      '<div class="field"><textarea class="rules" id="custom-rules" placeholder="' + T("cfg_extra_ph") + '">' + esc(st.CUSTOM_RULES) + "</textarea></div></section>";

    h += '</div><div><section class="preview"><div class="sec-head"><h2>' + T("cfg_preview") + '</h2><span class="state" id="pv-state"></span></div>' +
      '<pre id="pv">' + esc(previewText) + "</pre></section></div></div>";

    document.getElementById("app").innerHTML = h;
    renderState();
    renderFooter();
    window.scrollTo(0, y);
  }

  function renderState() {
    var el = document.getElementById("pv-state");
    if (el) el.innerHTML = busy ? T("cfg_preview_busy") : previewErr ? '<span style="color:var(--warn)">' + esc(previewErr) + "</span>" : T("cfg_preview_live");
    var pv = document.getElementById("pv");
    if (pv && pv.textContent !== previewText) pv.textContent = previewText;
  }

  function renderFooter(error) {
    document.getElementById("footer").innerHTML = '<div class="foot"><div class="sum">' + T("cfg_foot") +
      "<small>" + T("cfg_foot_hint") + "</small></div>" +
      '<button type="button" class="btn" id="cancel">' + T("cancel") + "</button>" +
      '<button type="button" class="btn primary" id="save">' + T("cfg_save") + "</button>" +
      (error ? '<div class="error" role="alert">' + esc(error) + "</div>" : "") + "</div>";
  }

  function payload() { return { settings: st }; }

  function refresh() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      busy = true; renderState();
      post("/preview", payload()).then(function (r) {
        busy = false;
        if (r.ok) {
          previewText = r.body.text; previewErr = "";
          var before = JSON.stringify(dirState); dirState = r.body.dirs || [];
          if (JSON.stringify(dirState) !== before && !document.activeElement.dataset.dir) { render(); return; }
        } else previewErr = r.body.error || "";
        renderState();
      }).catch(function () { busy = false; previewErr = MSG.err_conn; renderState(); });
    }, 250);
  }

  document.addEventListener("change", function (e) {
    var t = e.target, d = t.dataset;
    if (t.id === "ui-lang") { st.UI_LANG = t.value; useLang(t.value); render(); return refresh(); }
    if (t.type === "radio" && t.name === "skills-mode") {
      st.SKILLS = t.value === "all" ? "all" : DATA.skills.map(function (k) { return k.name; });
      render(); return refresh();
    }
    if (t.type === "radio" && st.hasOwnProperty(t.name)) { st[t.name] = t.value; return refresh(); }
    if (d.multi) {
      var arr = st[d.multi], i = arr.indexOf(t.value);
      if (t.checked && i < 0) arr.push(t.value);
      if (!t.checked && i >= 0) arr.splice(i, 1);
      if (d.multi === "STACKS" && st.SKILLS !== "all") render();
      return refresh();
    }
    if (d.skill) {
      var j = st.SKILLS.indexOf(d.skill);
      if (t.checked && j < 0) st.SKILLS.push(d.skill);
      if (!t.checked && j >= 0) st.SKILLS.splice(j, 1);
      return refresh();
    }
    if (d.lang) {
      if (t.value === "*") { st[d.lang] = ""; render(); var f = document.querySelector('[data-free="' + d.lang + '"]'); if (f) f.focus(); }
      else { st[d.lang] = t.value; render(); }
      return refresh();
    }
  });
  document.addEventListener("input", function (e) {
    var t = e.target, d = t.dataset;
    if (d.free) { st[d.free] = t.value; return refresh(); }
    if (t.id === "scaffold") { st.SCAFFOLD = t.value; return refresh(); }
    if (d.dir !== undefined) { st.DIRS[+d.dir] = t.value; return refresh(); }
    if (t.id === "custom-rules") { st.CUSTOM_RULES = t.value; return refresh(); }
  });
  // after leaving a folder field, re-render (to show "does not exist") once any click on another button has run
  document.addEventListener("focusout", function (e) {
    if (e.target.dataset && e.target.dataset.dir !== undefined) {
      setTimeout(function () { var a = document.activeElement; if (!a || !a.dataset || a.dataset.dir === undefined) render(); }, 150);
    }
  });
  // ---- folder picker ----
  var picker = null;
  function closePicker() {
    var m = document.getElementById("picker"); if (m) m.remove();
    picker = null;
  }
  function openPicker(k) {
    picker = { k: k, path: "", shown: "", parent: "", dirs: [], truncated: false };
    loadPicker(st.DIRS[k] || "");
  }
  function loadPicker(path) {
    post("/browse", { path: path }).then(function (r) {
      if (!picker) return;
      if (r.ok) {
        picker.path = r.body.path; picker.shown = r.body.shown; picker.parent = r.body.parent;
        picker.home = r.body.home; picker.dirs = r.body.dirs; picker.truncated = r.body.truncated;
      }
      drawPicker();
    });
  }
  function drawPicker() {
    var m = document.getElementById("picker");
    if (!m) { m = document.createElement("div"); m.id = "picker"; m.className = "modal-bg"; document.body.appendChild(m); }
    var list = picker.dirs.length ? picker.dirs.map(function (n) {
      return '<button type="button" data-go="' + esc(n) + '">📁 ' + esc(n) + "</button>";
    }).join("") + (picker.truncated ? '<div class="none">…</div>' : "") : '<div class="none">' + T("cfg_browse_empty") + "</div>";
    m.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-label="' + esc(T("cfg_browse_title")) + '">' +
      "<h3>" + T("cfg_browse_title") + "</h3>" +
      '<div class="bar"><button type="button" class="small" data-up="1"' + (picker.parent ? "" : " disabled") + ">" + T("cfg_browse_up") + "</button>" +
      '<button type="button" class="small" data-home="1">' + T("cfg_browse_home") + "</button>" +
      '<input type="text" id="picker-path" value="' + esc(picker.shown) + '" aria-label="' + esc(T("cfg_browse_path")) + '"></div>' +
      '<div class="list">' + list + "</div>" +
      '<div class="foot"><span class="cur" title="' + esc(picker.path) + '">' + esc(picker.shown) + "</span>" +
      '<button type="button" class="small" data-pcancel="1">' + T("cancel") + "</button>" +
      '<button type="button" class="btn primary" data-puse="1">' + T("cfg_browse_use") + "</button></div></div>";
  }
  document.addEventListener("keydown", function (e) {
    if (!picker) return;
    if (e.key === "Escape") { closePicker(); return; }
    if (e.key === "Enter" && e.target.id === "picker-path") { e.preventDefault(); loadPicker(e.target.value); }
  });
  document.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    if (picker && e.target.classList && e.target.classList.contains("modal-bg")) { closePicker(); return; }
    if (!t) return;
    if (t.dataset.choose !== undefined) { return openPicker(+t.dataset.choose); }
    if (t.dataset.go !== undefined) { return loadPicker(picker.path.replace(/\/+$/, "") + "/" + t.dataset.go); }
    if (t.dataset.up) { return loadPicker(picker.parent); }
    if (t.dataset.home) { return loadPicker(picker.home); }
    if (t.dataset.pcancel) { return closePicker(); }
    if (t.dataset.puse) {
      st.DIRS[picker.k] = picker.shown; closePicker(); render(); return refresh();
    }
    if (t.id === "theme") return toggleTheme();
    if (t.id === "add-dir") { st.DIRS.push(""); render(); var ins = document.querySelectorAll("[data-dir]"); if (ins.length) ins[ins.length - 1].focus(); return; }
    if (t.dataset.rmdir !== undefined) { st.DIRS.splice(+t.dataset.rmdir, 1); if (!st.DIRS.length) st.DIRS.push(""); render(); return refresh(); }
    if (t.id === "cancel") { post("/cancel").then(function () { finish(T("cancelled_title"), T("cfg_cancelled_text")); }); return; }
    if (t.id === "save") {
      t.disabled = true;
      post("/save", payload()).then(function (r) {
        if (r.ok) finish(T("cfg_saved_title"), T("cfg_saved_text"));
        else { renderFooter(r.body.error || MSG.err_submit); }
      }).catch(function () { renderFooter(MSG.err_conn); });
    }
  });

  render();
  refresh();
})();
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True)
    p.add_argument("--home", default=os.path.expanduser("~"))
    p.add_argument("--machine", required=True)
    p.add_argument("--profile-dir", required=True)
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args()
    app = Config(args)
    return ui_common.serve(app, app.msg, no_open=args.no_open, port=args.port)


if __name__ == "__main__":
    sys.exit(main())
