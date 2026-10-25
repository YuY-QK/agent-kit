#!/usr/bin/env bash
# Add agent-kit's project template to a project: AGENTS.md, CLAUDE.md, docs/AI_RULES.md, docs/progress.md.
# Existing files are never overwritten. The template language follows CONTENT_LANG
# in your profile; pass --lang to choose another one.
#
# Usage:
#   scripts/new-project.sh <project-folder> [project-name] [--lang en|zh-CN] [--cloud] [--with-profile]
#
# --cloud           also set up Claude Code on the web (runs scripts/enable-cloud.sh)
# --with-profile    with --cloud: copy your profile into the project too
#
# The project name defaults to the folder name. Afterwards, fill in the parts marked {{...}}.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"
load_settings
load_messages "$UI_LANG"

LANG_CHOICE="$CONTENT_LANG"
ARGS=""
CLOUD=0
CLOUD_ARGS=""
PROJECT_DIR=""
PROJECT_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --cloud) CLOUD=1 ;;
    --with-profile) CLOUD=1; CLOUD_ARGS="--with-profile" ;;
    --lang) shift; LANG_CHOICE="${1:-$CONTENT_LANG}" ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *)
      if [ -z "$PROJECT_DIR" ]; then PROJECT_DIR="$1"
      elif [ -z "$PROJECT_NAME" ]; then PROJECT_NAME="$1"
      fi
      ;;
  esac
  shift
done

if [ -z "$PROJECT_DIR" ]; then
  sed -n '2,13p' "$0"
  exit 2
fi
if [ ! -d "$PROJECT_DIR" ]; then
  say folder_not_found "$PROJECT_DIR" >&2
  exit 1
fi
TEMPLATE_DIR="$KIT_DIR/templates/project/$LANG_CHOICE"
[ -d "$TEMPLATE_DIR" ] || TEMPLATE_DIR="$KIT_DIR/templates/project/en"
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$PROJECT_DIR")}"

# escape / & \ in the name so it can't break the sed expression
escaped_name="$(printf '%s' "$PROJECT_NAME" | sed 's/[\/&\\]/\\&/g')"

(cd "$TEMPLATE_DIR" && find . -type f) | while read -r rel; do
  rel="${rel#./}"
  dest="$PROJECT_DIR/$rel"
  if [ -e "$dest" ]; then
    say template_exists "$rel"
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  sed "s/{{PROJECT_NAME}}/$escaped_name/g" "$TEMPLATE_DIR/$rel" > "$dest"
  say template_created "$rel"
done

say template_done

if [ "$CLOUD" -eq 1 ]; then
  echo
  # shellcheck disable=SC2086
  "$KIT_DIR/scripts/enable-cloud.sh" "$PROJECT_DIR" $CLOUD_ARGS
fi
