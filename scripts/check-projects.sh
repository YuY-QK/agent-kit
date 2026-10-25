#!/usr/bin/env bash
# Check whether your projects follow agent-kit's project-layer conventions.
# Reports only; never changes files.
#
# Checks:
#   - the project has an AGENTS.md
#   - the project has a CLAUDE.md that references @AGENTS.md (so Claude Code reads the same rules)
#   - the project has no copies of shared skills under the same name (they would clash)
#
# Usage:
#   scripts/check-projects.sh                  check every project under PROJECT_DIRS (machine settings)
#   scripts/check-projects.sh <project>...     check only these projects
#
# A subfolder counts as a project if it contains .git, AGENTS.md or CLAUDE.md.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"
load_settings
load_messages "$UI_LANG"

KIT_SKILLS=" $(repo_skill_names | tr '\n' ' ') "

check_project() {
  dir="$1"
  issues=""
  [ -f "$dir/AGENTS.md" ] || issues="$issues
  - $(t chk_no_agents)"
  if [ ! -f "$dir/CLAUDE.md" ]; then
    issues="$issues
  - $(t chk_no_claude)"
  elif [ -f "$dir/AGENTS.md" ] && ! grep -q '@AGENTS.md' "$dir/CLAUDE.md"; then
    issues="$issues
  - $(t chk_claude_no_import)"
  fi
  for skills_dir in "$dir/.agents/skills" "$dir/.claude/skills"; do
    [ -d "$skills_dir" ] || continue
    for s in "$skills_dir"/*/; do
      [ -d "$s" ] || continue
      name="$(basename "$s")"
      case "$KIT_SKILLS" in
        *" $name "*) issues="$issues
  - $(t chk_same_name "${skills_dir#"$dir"/}/$name")" ;;
      esac
    done
  done
  if [ -z "$issues" ]; then
    printf '✓ %s\n' "$(basename "$dir")"
  else
    printf '✗ %s%s\n' "$(basename "$dir")" "$issues"
  fi
}

case "${1:-}" in -h|--help) sed -n '2,15p' "$0"; exit 0 ;; esac

if [ $# -gt 0 ]; then
  for d in "$@"; do
    if [ -d "$d" ]; then
      check_project "$(cd "$d" && pwd -P)"
    else
      say folder_not_found "$d" >&2
    fi
  done
  exit 0
fi

if [ -z "$PROJECT_DIRS" ]; then
  say chk_no_dirs >&2
  exit 2
fi

old_ifs="$IFS"; IFS=":"
set -f
roots="$(for r in $PROJECT_DIRS; do printf '%s\n' "$r"; done)"
set +f
IFS="$old_ifs"

printf '%s\n' "$roots" | while IFS= read -r root; do
  [ -n "$root" ] || continue
  if [ ! -d "$root" ]; then say chk_dir_missing "$root" >&2; continue; fi
  found=0
  for d in "$root"/*/; do
    [ -d "$d" ] || continue
    d="${d%/}"
    if [ -d "$d/.git" ] || [ -f "$d/AGENTS.md" ] || [ -f "$d/CLAUDE.md" ]; then
      check_project "$d"
      found=1
    fi
  done
  [ "$found" -eq 1 ] || say chk_none_found "$root"
done
