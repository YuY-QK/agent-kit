#!/usr/bin/env bash
# Set up a new project repository in one go: clone it, add agent-kit's project template and
# the cloud-session hook, then (with --push) commit and push. Safe to run again: existing
# files are never overwritten, and nothing is committed when nothing changed.
# The start-project skill runs this for you.
#
# Usage:
#   scripts/bootstrap-project.sh <repo> [options]
#
#   <repo>   an existing local checkout, a Git URL (git@github.com:owner/app.git, https://...)
#            or owner/app (cloned over SSH from GitHub)
#
# Options:
#   --dir <folder>          where to clone (default: ./<repo name>)
#   --name <name>           project name in the templates (default: the repo name)
#   --lang en|zh-CN         template language (default: CONTENT_LANG in your profile)
#   --profile copy|repo|none
#                           settings for cloud sessions (default: none)
#                             copy  copy your profile into the project (.claude/agent-kit/);
#                                   committed with it, so only for private projects
#                             repo  write your profile repository's URL into the project, so
#                                   cloud sessions clone it (they need access to that repo)
#                             none  cloud sessions use agent-kit's defaults
#   --no-cloud              don't add the cloud-session hook
#   --branch <name>         branch to commit to (default: the current one, or main if empty)
#   --push                  commit the changes and push them
#   --message <text>        commit message (default: "Set up agent-kit project files")

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"
load_settings
load_messages "$UI_LANG"

usage() { sed -n '2,27p' "$0"; }

REPO=""; DIR=""; NAME=""; LANG_CHOICE="$CONTENT_LANG"; PROFILE_MODE="none"
CLOUD=1; BRANCH=""; PUSH=0; MESSAGE="Set up agent-kit project files"
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) shift; DIR="${1:-}" ;;
    --name) shift; NAME="${1:-}" ;;
    --lang) shift; LANG_CHOICE="${1:-$CONTENT_LANG}" ;;
    --profile) shift; PROFILE_MODE="${1:-}" ;;
    --no-cloud) CLOUD=0 ;;
    --branch) shift; BRANCH="${1:-}" ;;
    --push) PUSH=1 ;;
    --message) shift; MESSAGE="${1:-$MESSAGE}" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) REPO="$1" ;;
  esac
  shift
done
[ -n "$REPO" ] || { usage >&2; exit 2; }
case "$PROFILE_MODE" in copy|repo|none) ;; *) echo "--profile must be copy, repo or none" >&2; exit 2 ;; esac
command -v git >/dev/null 2>&1 || { say boot_need_git >&2; exit 1; }

# ---------- get the checkout ----------
if [ -d "$REPO" ] && [ "$(git -C "$REPO" rev-parse --is-bare-repository 2>/dev/null)" != "true" ]; then
  PROJECT="$REPO"
else
  url="$REPO"
  case "$url" in
    *://*|git@*:*|/*) ;;
    */*) url="git@github.com:${url%.git}.git" ;;
    *) say folder_not_found "$REPO" >&2; exit 1 ;;
  esac
  repo_name="$(basename "${url%.git}")"
  PROJECT="${DIR:-$repo_name}"
  if [ -d "$PROJECT/.git" ]; then
    say boot_clone_exists "$PROJECT"
  else
    say boot_cloning "$url"
    git clone -q "$url" "$PROJECT" 2>&1 | grep -v 'appear to have cloned an empty' >&2 || true
    [ -d "$PROJECT/.git" ] || { say boot_clone_failed "$url" >&2; exit 1; }
  fi
fi
PROJECT="$(cd "$PROJECT" && pwd -P)"
[ -d "$PROJECT/.git" ] || { say boot_not_git "$PROJECT" >&2; exit 1; }
NAME="${NAME:-$(basename "$PROJECT")}"

# empty repository: start the branch
if ! git -C "$PROJECT" rev-parse -q --verify HEAD >/dev/null 2>&1; then
  git -C "$PROJECT" symbolic-ref HEAD "refs/heads/${BRANCH:-main}"
  say boot_empty "${BRANCH:-main}"
elif [ -n "$BRANCH" ] && [ "$(git -C "$PROJECT" rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
  if git -C "$PROJECT" rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
    git -C "$PROJECT" checkout -q "$BRANCH"
  elif git -C "$PROJECT" rev-parse -q --verify "refs/remotes/origin/$BRANCH" >/dev/null; then
    git -C "$PROJECT" checkout -q -b "$BRANCH" "origin/$BRANCH"
  else
    git -C "$PROJECT" checkout -q -b "$BRANCH"
  fi
fi
BRANCH="$(git -C "$PROJECT" symbolic-ref --short HEAD)"

# ---------- project files ----------
echo
"$KIT_DIR/scripts/new-project.sh" "$PROJECT" "$NAME" --lang "$LANG_CHOICE"

if [ "$CLOUD" -eq 1 ]; then
  echo
  if [ "$PROFILE_MODE" = "copy" ]; then
    AGENT_KIT_BOOTSTRAP=1 "$KIT_DIR/scripts/enable-cloud.sh" "$PROJECT" --with-profile
  else
    AGENT_KIT_BOOTSTRAP=1 "$KIT_DIR/scripts/enable-cloud.sh" "$PROJECT"
  fi
  if [ "$PROFILE_MODE" != "copy" ] && [ -f "$PROJECT/.claude/agent-kit/profile.sh" ]; then
    say boot_copy_left >&2
  fi
  if [ "$PROFILE_MODE" = "repo" ]; then
    purl="$(git -C "$PROFILE_DIR" remote get-url origin 2>/dev/null || true)"
    case "$purl" in
      git@github.com:*) purl="https://github.com/${purl#git@github.com:}" ;;
      ssh://git@github.com/*) purl="https://github.com/${purl#ssh://git@github.com/}" ;;
    esac
    if [ -z "$purl" ]; then
      say boot_no_profile_repo >&2
    else
      mkdir -p "$PROJECT/.claude/agent-kit"
      printf '%s\n' "$purl" > "$PROJECT/.claude/agent-kit/profile-repo"
      say boot_profile_repo "$purl"
    fi
  fi
fi

# ---------- commit and push ----------
echo
if [ "$PUSH" -eq 0 ]; then
  say boot_ready "$PROJECT"
  exit 0
fi
git -C "$PROJECT" add -A
if git -C "$PROJECT" diff --cached --quiet 2>/dev/null &&
   git -C "$PROJECT" rev-parse -q --verify HEAD >/dev/null 2>&1; then
  say boot_nothing
else
  git -C "$PROJECT" commit -q -m "$MESSAGE"
  say boot_committed "$BRANCH"
fi
if git -C "$PROJECT" remote get-url origin >/dev/null 2>&1; then
  if git -C "$PROJECT" push -q -u origin "HEAD:$BRANCH"; then
    say boot_pushed "$BRANCH"
  else
    say boot_push_failed >&2
    exit 1
  fi
else
  say boot_no_remote
fi
