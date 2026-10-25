#!/usr/bin/env bash
# Write profile.sh and machine.sh from AK_SET_* environment variables.
# Used by the web settings form so both the terminal and the web page share one file format.
# Not meant to be run by hand.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/../.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"

load_settings
for k in $OPT_PROFILE_KEYS; do
  eval "v=\${AK_SET_$k-__unset__}"
  if [ "$v" != "__unset__" ]; then
    safe_value "$v" || { echo "unsafe value for $k" >&2; exit 2; }
    eval "$k=\$v"
  fi
done

CUSTOM_PROFILE_DIR=""
[ -n "${M_HAS_PROFILE_DIR:-}" ] && CUSTOM_PROFILE_DIR="$(to_config_path "$PROFILE_DIR")"
if [ "${AK_SET_PROJECT_DIRS-__unset__}" != "__unset__" ]; then
  PROJECT_DIRS="$AK_SET_PROJECT_DIRS"
else
  dirs=""; old_ifs="$IFS"; IFS=":"
  for d in $PROJECT_DIRS; do dirs="${dirs:+$dirs:}$(to_config_path "$d")"; done
  IFS="$old_ifs"
  PROJECT_DIRS="$dirs"
fi
safe_value "$PROJECT_DIRS" || { echo "unsafe project folders" >&2; exit 2; }

write_profile
write_machine
if [ -n "$LEGACY_LOADED" ] && [ -f "$LEGACY_CONFIG" ]; then
  mkdir -p "$BACKUP_ROOT"
  mv "$LEGACY_CONFIG" "$BACKUP_ROOT/config.sh.migrated-$(date +%Y%m%d-%H%M%S)"
fi
