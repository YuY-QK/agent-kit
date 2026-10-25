#!/usr/bin/env bash
# Keep your agent-kit profile in a private Git repository and sync it between computers.
#
# Usage:
#   scripts/sync-profile.sh status          show where the profile is and whether it has changes
#   scripts/sync-profile.sh init GIT_URL    turn the current profile into a repository and push it
#                                           to GIT_URL (an empty private repository you created)
#   scripts/sync-profile.sh clone GIT_URL   use the profile from GIT_URL on this computer
#   scripts/sync-profile.sh pull            get the latest profile
#   scripts/sync-profile.sh push [MESSAGE]  commit and push your profile changes
#
# Compatible with bash 3.2.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"

load_settings
load_messages "$UI_LANG"

cmd="${1:-status}"
[ $# -gt 0 ] && shift

need_git() {
  command -v git >/dev/null 2>&1 || { say git_missing >&2; exit 1; }
}
is_repo() {
  [ -d "$PROFILE_DIR/.git" ]
}

case "$cmd" in
  status)
    say profile_location "$(pretty "$PROFILE_DIR")"
    if [ ! -f "$PROFILE_FILE" ]; then say profile_missing; exit 0; fi
    if is_repo; then
      need_git
      remote="$(git -C "$PROFILE_DIR" remote get-url origin 2>/dev/null || true)"
      say profile_remote "${remote:--}"
      changes="$(git -C "$PROFILE_DIR" status --short)"
      if [ -n "$changes" ]; then say profile_has_changes; printf '%s\n' "$changes" | sed 's/^/  /'; else say profile_clean; fi
    else
      say profile_not_synced
    fi
    ;;

  init)
    need_git
    url="${1:-}"
    [ -n "$url" ] || { say need_git_url >&2; exit 2; }
    [ -f "$PROFILE_FILE" ] || { say profile_missing >&2; exit 1; }
    if is_repo; then
      if git -C "$PROFILE_DIR" remote get-url origin >/dev/null 2>&1; then
        git -C "$PROFILE_DIR" remote set-url origin "$url"
      else
        git -C "$PROFILE_DIR" remote add origin "$url"
      fi
    else
      git -C "$PROFILE_DIR" init -q
      git -C "$PROFILE_DIR" checkout -q -b main 2>/dev/null || true
      git -C "$PROFILE_DIR" remote add origin "$url"
    fi
    git -C "$PROFILE_DIR" add -A
    if [ -n "$(git -C "$PROFILE_DIR" status --porcelain)" ]; then
      git -C "$PROFILE_DIR" commit -q -m "chore: agent-kit profile"
    fi
    branch="$(git -C "$PROFILE_DIR" rev-parse --abbrev-ref HEAD)"
    if git -C "$PROFILE_DIR" push -u origin "$branch"; then
      say profile_pushed "$url"
    else
      say push_failed_hint >&2
      exit 1
    fi
    ;;

  clone)
    need_git
    url="${1:-}"
    [ -n "$url" ] || { say need_git_url >&2; exit 2; }
    if is_repo; then
      current="$(git -C "$PROFILE_DIR" remote get-url origin 2>/dev/null || true)"
      if [ "$current" = "$url" ]; then
        git -C "$PROFILE_DIR" pull -q --ff-only
        say profile_updated "$(pretty "$PROFILE_DIR")"
        exit 0
      fi
    fi
    if [ -e "$PROFILE_DIR" ] && [ -n "$(ls -A "$PROFILE_DIR" 2>/dev/null)" ]; then
      backup="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)/profile"
      mkdir -p "$(dirname "$backup")"
      mv "$PROFILE_DIR" "$backup"
      say profile_backed_up "$(pretty "$backup")"
    fi
    mkdir -p "$(dirname "$PROFILE_DIR")"
    rm -rf "$PROFILE_DIR"
    git clone -q "$url" "$PROFILE_DIR"
    say profile_cloned "$(pretty "$PROFILE_DIR")"
    ;;

  pull)
    need_git
    is_repo || { say profile_not_synced >&2; exit 1; }
    git -C "$PROFILE_DIR" pull --ff-only
    ;;

  push)
    need_git
    is_repo || { say profile_not_synced >&2; exit 1; }
    msg="${1:-chore: update agent-kit profile}"
    git -C "$PROFILE_DIR" add -A
    if [ -n "$(git -C "$PROFILE_DIR" status --porcelain)" ]; then
      git -C "$PROFILE_DIR" commit -q -m "$msg"
    fi
    git -C "$PROFILE_DIR" push
    say profile_pushed "$(git -C "$PROFILE_DIR" remote get-url origin 2>/dev/null || echo origin)"
    ;;

  -h|--help|help)
    sed -n '2,12p' "$0"
    ;;

  *)
    echo "unknown command: $cmd" >&2
    sed -n '2,12p' "$0" >&2
    exit 2
    ;;
esac
