#!/usr/bin/env bash
# Let Claude Code on the web use agent-kit in a project.
#
# Cloud sessions start in a fresh container without your global rules and skills. This adds
# a SessionStart hook to the project that installs agent-kit when a cloud session starts.
# Commit the added files to the project afterwards.
#
# Usage:
#   scripts/enable-cloud.sh <project-folder>                  add or update the hook
#   scripts/enable-cloud.sh <project-folder> --with-profile   also copy your profile into the
#                                                             project (.claude/agent-kit/), so cloud
#                                                             sessions use your languages and rules
#
# Adds:
#   .claude/hooks/agent-kit-session-start.sh   the hook (does nothing outside cloud sessions)
#   .claude/settings.json                      SessionStart entry, merged into existing settings
#   .claude/agent-kit/                         with --with-profile: profile.sh and rules/*.md
#
# The cloud has to be able to clone agent-kit, so the agent-kit repository must be public
# (or set AGENT_KIT_REPO in the cloud environment to a URL it can reach).

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"

load_settings
load_messages "$UI_LANG"

PROJECT=""
WITH_PROFILE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --with-profile) WITH_PROFILE=1 ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; sed -n '2,21p' "$0" >&2; exit 2 ;;
    *) PROJECT="$1" ;;
  esac
  shift
done
[ -n "$PROJECT" ] || { sed -n '2,21p' "$0" >&2; exit 2; }
[ -d "$PROJECT" ] || { say folder_not_found "$PROJECT" >&2; exit 1; }
PROJECT="$(cd "$PROJECT" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { say cloud_need_python >&2; exit 1; }

# The URL the cloud clones agent-kit from: this repository's remote, as HTTPS.
remote="$(git -C "$KIT_DIR" remote get-url origin 2>/dev/null || true)"
case "$remote" in
  git@github.com:*) remote="https://github.com/${remote#git@github.com:}" ;;
  ssh://git@github.com/*) remote="https://github.com/${remote#ssh://git@github.com/}" ;;
esac
[ -n "$remote" ] || remote="https://github.com/YuY-QK/agent-kit"

hook_rel=".claude/hooks/agent-kit-session-start.sh"
mkdir -p "$PROJECT/.claude/hooks"
tmp="$PROJECT/$hook_rel.tmp"
awk -v url="$remote" '{ gsub(/__AGENT_KIT_REPO__/, url); print }' \
  "$KIT_DIR/templates/cloud/agent-kit-session-start.sh" > "$tmp"
chmod +x "$tmp"
if [ -f "$PROJECT/$hook_rel" ] && cmp -s "$tmp" "$PROJECT/$hook_rel"; then
  rm "$tmp"; say cloud_hook_same "$hook_rel"
else
  existed=0; [ -f "$PROJECT/$hook_rel" ] && existed=1
  mv "$tmp" "$PROJECT/$hook_rel"
  if [ "$existed" -eq 1 ]; then say cloud_hook_updated "$hook_rel"; else say cloud_hook_added "$hook_rel"; fi
fi

# Merge the SessionStart entry into .claude/settings.json, keeping everything else.
result="$(python3 - "$PROJECT/.claude/settings.json" <<'PY'
import json, os, sys
path = sys.argv[1]
cmd = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/agent-kit-session-start.sh'
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        print("invalid")
        sys.exit(0)
hooks = data.setdefault("hooks", {})
entries = hooks.setdefault("SessionStart", [])
for e in entries:
    for h in e.get("hooks", []):
        if "agent-kit-session-start.sh" in h.get("command", ""):
            print("present")
            sys.exit(0)
entries.append({"hooks": [{"type": "command", "command": cmd, "timeout": 180}]})
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("added")
PY
)"
case "$result" in
  added) say cloud_settings_added ".claude/settings.json" ;;
  present) say cloud_settings_present ".claude/settings.json" ;;
  invalid) say cloud_settings_invalid ".claude/settings.json" >&2; exit 1 ;;
esac

if [ "$WITH_PROFILE" -eq 1 ]; then
  [ -f "$PROFILE_FILE" ] || { say profile_missing >&2; exit 1; }
  dest="$PROJECT/.claude/agent-kit"
  mkdir -p "$dest"
  cp "$PROFILE_FILE" "$dest/profile.sh"
  say cloud_copied ".claude/agent-kit/profile.sh"
  if ls "$PROFILE_DIR"/rules/*.md >/dev/null 2>&1; then
    mkdir -p "$dest/rules"
    for f in "$PROFILE_DIR"/rules/*.md; do
      cp "$f" "$dest/rules/"
      say cloud_copied ".claude/agent-kit/rules/$(basename "$f")"
    done
  fi
  say cloud_profile_public
fi

if [ -z "${AGENT_KIT_BOOTSTRAP:-}" ]; then
  echo
  say cloud_next "$remote"
fi
