# Shared helpers for agent-kit scripts. Source it; don't run it.
# Compatible with bash 3.2 (the version that ships with macOS).

KIT_DIR="${KIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
CONFIG_HOME="${AGENT_KIT_HOME:-$HOME/.config/agent-kit}"
MACHINE_FILE="${AGENT_KIT_MACHINE:-$CONFIG_HOME/machine.sh}"
LEGACY_CONFIG="$CONFIG_HOME/config.sh"
BUILD_DIR="$CONFIG_HOME/build"
STATE_DIR="$CONFIG_HOME/state"
BACKUP_ROOT="$CONFIG_HOME/backups"

# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/options.sh"

# ---------- output ----------

# Path for display: $HOME/... becomes ~/...
pretty() {
  case "$1" in
    "$HOME") printf '~' ;;
    "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# Path for config files: $HOME/... is written as $HOME/... so it survives a different user name.
to_config_path() {
  case "$1" in
    "$HOME") printf '$HOME' ;;
    "$HOME"/*) printf '$HOME/%s' "${1#"$HOME"/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# ---------- i18n ----------

system_lang() {
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    zh_CN*|zh_SG*|zh-CN*|zh_Hans*) echo zh-CN ;;
    zh*) echo zh-CN ;;
    *) echo en ;;
  esac
}

# Load messages for the UI language (falls back to English for missing keys).
load_messages() {
  lang="${1:-en}"
  # shellcheck disable=SC1090
  . "$KIT_DIR/scripts/i18n/en.sh"
  if [ "$lang" != "en" ] && [ -f "$KIT_DIR/scripts/i18n/$lang.sh" ]; then
    # shellcheck disable=SC1090
    . "$KIT_DIR/scripts/i18n/$lang.sh"
  fi
  UI_LANG_LOADED="$lang"
}

# t KEY [ARGS...]: print a translated message (printf format) without a newline.
t() {
  key="M_$1"
  shift
  eval "fmt=\${$key:-$key}"
  # shellcheck disable=SC2059
  printf "$fmt" "$@"
}
# say KEY [ARGS...]: same as t, plus a newline.
say() {
  t "$@"
  printf '\n'
}

# ---------- config files ----------

# Read KEY="value" lines from a shell config file without executing anything else.
# Values may reference $HOME. Prints nothing; sets variables named PREFIX_KEY.
read_kv_file() {
  file="$1"
  prefix="$2"
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|'#'*) continue ;;
    esac
    k="${line%%=*}"
    v="${line#*=}"
    case "$k" in
      *[!A-Z0-9_]*|'') continue ;;
    esac
    # strip one level of surrounding quotes
    case "$v" in
      \"*\") v="${v#\"}"; v="${v%\"}" ;;
      \'*\') v="${v#\'}"; v="${v%\'}" ;;
    esac
    # expand a leading or embedded $HOME only
    v="$(printf '%s' "$v" | sed "s#\\\$HOME#$(printf '%s' "$HOME" | sed 's/[#&\\]/\\&/g')#g")"
    eval "${prefix}_${k}=\$v"
    eval "${prefix}_HAS_${k}=1"
  done < "$file"
}

# Values written to config files may not contain characters that break the format.
safe_value() {
  case "$1" in
    *\"*|*\`*|*\\*|*'$('*) return 1 ;;
  esac
  return 0
}

# ---------- machine and profile ----------

repo_stacks() {
  for d in "$KIT_DIR"/stacks/*/; do
    [ -d "$d" ] && basename "$d"
  done
  return 0
}

# Every skill name in the repository (shared and stack skills).
repo_skill_names() {
  for f in "$KIT_DIR"/skills/*/SKILL.md "$KIT_DIR"/stacks/*/skills/*/SKILL.md; do
    [ -f "$f" ] && basename "$(dirname "$f")"
  done
  return 0
}

# Load the machine config (with migration from the legacy config.sh) and the profile.
# Sets: PROJECT_DIRS PROFILE_DIR PROFILE_FILE, and every profile key (with defaults),
# plus MISSING_KEYS: profile/machine keys that were not set in the files.
load_settings() {
  M_PROJECT_DIRS=""; M_PROFILE_DIR=""
  M_HAS_PROJECT_DIRS=""; M_HAS_PROFILE_DIR=""
  read_kv_file "$MACHINE_FILE" M
  LEGACY_LOADED=""
  if [ ! -f "$MACHINE_FILE" ] && [ -f "$LEGACY_CONFIG" ]; then
    L_PROJECT_DIRS=""; L_AGENT_TOOLS=""; L_STACKS=""
    read_kv_file "$LEGACY_CONFIG" L
    LEGACY_LOADED=1
    if [ -n "${L_HAS_PROJECT_DIRS:-}" ]; then
      # the legacy format separated directories with spaces
      M_PROJECT_DIRS="$(printf '%s' "$L_PROJECT_DIRS" | tr ' ' ':')"
      M_HAS_PROJECT_DIRS=1
    fi
  fi
  PROJECT_DIRS="$M_PROJECT_DIRS"
  PROFILE_DIR="${AGENT_KIT_PROFILE:-${M_PROFILE_DIR:-$CONFIG_HOME/profile}}"
  PROFILE_FILE="$PROFILE_DIR/profile.sh"

  for k in $OPT_PROFILE_KEYS; do
    eval "P_$k=''; P_HAS_$k=''"
  done
  read_kv_file "$PROFILE_FILE" P
  if [ -n "$LEGACY_LOADED" ] && [ ! -f "$PROFILE_FILE" ]; then
    [ -n "${L_HAS_AGENT_TOOLS:-}" ] && { P_TOOLS="$L_AGENT_TOOLS"; P_HAS_TOOLS=1; }
    [ -n "${L_HAS_STACKS:-}" ] && { P_STACKS="$L_STACKS"; P_HAS_STACKS=1; }
  fi

  MISSING_KEYS=""
  [ -n "$M_HAS_PROJECT_DIRS" ] || MISSING_KEYS="$MISSING_KEYS PROJECT_DIRS"
  for k in $OPT_PROFILE_KEYS; do
    eval "has=\$P_HAS_$k"
    [ -n "$has" ] || MISSING_KEYS="$MISSING_KEYS $k"
  done

  sys="$(system_lang)"
  UI_LANG="${P_UI_LANG:-$sys}"
  CONTENT_LANG="${P_CONTENT_LANG:-$OPT_CONTENT_LANG_DEFAULT}"
  REPLY_LANG="${P_REPLY_LANG:-$UI_LANG}"
  DOCS_LANG="${P_DOCS_LANG:-$OPT_DOCS_LANG_DEFAULT}"
  WORK_MODE="${P_WORK_MODE:-$OPT_WORK_MODE_DEFAULT}"
  DESIGN="${P_DESIGN:-$OPT_DESIGN_DEFAULT}"
  PLANNING="${P_PLANNING:-$OPT_PLANNING_DEFAULT}"
  COMMITS="${P_COMMITS:-$OPT_COMMITS_DEFAULT}"
  SCAFFOLD="${P_SCAFFOLD:-$OPT_SCAFFOLD_DEFAULT}"
  if [ -n "$P_HAS_STACKS" ]; then STACKS="$P_STACKS"; else STACKS="$(repo_stacks | tr '\n' ' ' | sed 's/ $//')"; fi
  SKILLS="${P_SKILLS:-$OPT_SKILLS_DEFAULT}"
  TOOLS="${P_TOOLS:-$OPT_TOOLS_DEFAULT}"
  # unknown content language falls back to English
  [ -d "$KIT_DIR/rules/$CONTENT_LANG" ] || CONTENT_LANG=en
  return 0
}

write_machine() {
  mkdir -p "$(dirname "$MACHINE_FILE")"
  {
    echo "# agent-kit machine settings for this computer only. Do not commit or sync."
    echo "# Edit by running scripts/configure.sh, or change the values below."
    echo "MACHINE_VERSION=\"$MACHINE_FORMAT_VERSION\""
    echo
    echo "# Folders that hold your projects, separated by colons (used by check-projects.sh)"
    echo "PROJECT_DIRS=\"$PROJECT_DIRS\""
    if [ -n "${CUSTOM_PROFILE_DIR:-}" ]; then
      echo
      echo "# Where your profile lives (default: ~/.config/agent-kit/profile)"
      echo "PROFILE_DIR=\"$CUSTOM_PROFILE_DIR\""
    fi
  } > "$MACHINE_FILE"
}

write_profile() {
  mkdir -p "$PROFILE_DIR"
  {
    echo "# agent-kit profile: your preferences. Safe to sync across computers"
    echo "# (for example in a private Git repository). Contains no machine paths."
    echo "# Edit by running scripts/configure.sh, or change the values below."
    echo "PROFILE_VERSION=\"$PROFILE_FORMAT_VERSION\""
    echo
    echo "# Language of the installer and web pages: en | zh-CN"
    echo "UI_LANG=\"$UI_LANG\""
    echo "# Language of the rules and skills content: en | zh-CN"
    echo "CONTENT_LANG=\"$CONTENT_LANG\""
    echo "# Language the assistant replies in: a code (en, zh-CN, ja, ...) or any language name"
    echo "REPLY_LANG=\"$REPLY_LANG\""
    echo "# Language for documents, comments and commit messages: reply (same as replies), or a code/name"
    echo "DOCS_LANG=\"$DOCS_LANG\""
    echo
    echo "# solo | team"
    echo "WORK_MODE=\"$WORK_MODE\""
    echo "# Design experience: none | some"
    echo "DESIGN=\"$DESIGN\""
    echo "# Plan before building: full | light | off"
    echo "PLANNING=\"$PLANNING\""
    echo "# Commit messages: conventional | free"
    echo "COMMITS=\"$COMMITS\""
    echo "# Your own project scaffold, if any (free text, empty for none)"
    echo "SCAFFOLD=\"$SCAFFOLD\""
    echo
    echo "# Stack skills to install, separated by spaces"
    echo "STACKS=\"$STACKS\""
    echo "# Skills to install: all, or names separated by spaces"
    echo "SKILLS=\"$SKILLS\""
    echo "# Tools to install for: claude codex"
    echo "TOOLS=\"$TOOLS\""
  } > "$PROFILE_FILE"
  # describe the profile folder (README in English and Chinese), without replacing your own
  for f in README.md README.zh-CN.md; do
    [ -f "$PROFILE_DIR/$f" ] || [ ! -f "$KIT_DIR/templates/profile/$f" ] ||
      cp "$KIT_DIR/templates/profile/$f" "$PROFILE_DIR/$f"
  done
}

# ---------- misc ----------

hash_file() {
  if [ ! -f "$1" ]; then echo "-"; return; fi
  if command -v shasum >/dev/null 2>&1; then
    LC_ALL=C shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    cksum "$1" | awk '{print $1 "-" $2}'
  fi
}

is_git_url() {
  case "$1" in
    *://*|git@*|*.git) return 0 ;;
  esac
  return 1
}

interactive() {
  [ -t 0 ] || [ "${AGENT_KIT_PROMPT:-0}" = "1" ]
}

web_available() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import http.server, difflib, json' >/dev/null 2>&1
}
