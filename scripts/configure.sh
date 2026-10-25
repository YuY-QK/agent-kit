#!/usr/bin/env bash
# Answer a few questions to create or change your agent-kit settings.
#
# Usage:
#   scripts/configure.sh            ask every question in the terminal (Enter keeps the current value)
#   scripts/configure.sh --web      use the web form instead (needs python3)
#   scripts/configure.sh --missing  ask only questions that have no answer yet
#
# Writes two files:
#   <profile>/profile.sh                 your preferences; safe to sync between computers
#   ~/.config/agent-kit/machine.sh       this computer only (project folders, profile location)
#
# Compatible with bash 3.2.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"

USE_WEB=0
ONLY_MISSING=0
for arg in ${1+"$@"}; do
  case "$arg" in
    --web) USE_WEB=1 ;;
    --missing) ONLY_MISSING=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

load_settings
load_messages "$UI_LANG"
CUSTOM_PROFILE_DIR=""
[ -n "${M_HAS_PROFILE_DIR:-}" ] && CUSTOM_PROFILE_DIR="$(to_config_path "$PROFILE_DIR")"

if [ "$ONLY_MISSING" -eq 1 ] && [ -z "$(echo $MISSING_KEYS)" ]; then
  exit 0
fi

if [ "$USE_WEB" -eq 1 ]; then
  if web_available; then
    exec python3 "$KIT_DIR/scripts/lib/config_ui.py" --kit "$KIT_DIR" --home "$HOME" \
      --machine "$MACHINE_FILE" --profile-dir "$PROFILE_DIR"
  fi
  say no_python_terminal
fi

# ---------- prompts ----------

ask() {
  if [ -t 0 ]; then
    read -r -e -p "$1" REPLY || REPLY=""
  else
    printf '%s' "$1"
    read -r REPLY || REPLY=""
    echo
  fi
}

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

needs() {
  # needs KEY: should this question be asked?
  [ "$ONLY_MISSING" -eq 0 ] && return 0
  case " $MISSING_KEYS " in *" $1 "*) return 0 ;; esac
  return 1
}

skill_description() {
  for d in "$KIT_DIR"/skills/"$1" "$KIT_DIR"/stacks/*/skills/"$1"; do
    [ -d "$d" ] || continue
    f="$d/SKILL.md"
    [ -f "$d/SKILL.$UI_LANG.md" ] && f="$d/SKILL.$UI_LANG.md"
    desc="$(sed -n 's/^description: *//p' "$f" | head -1)"
    # first sentence only, at most 70 characters
    desc="${desc%%。*}"; desc="${desc%%. *}"
    [ "${#desc}" -gt 70 ] && desc="${desc:0:70}…"
    printf '%s' "$desc"
    return 0
  done
}

label_of() {
  # label_of KEY VALUE
  if [ "$1" = "SKILL" ]; then
    printf '%-22s %s' "$2" "$(skill_description "$2")"
    return
  fi
  v="$(printf '%s' "$2" | tr '-' '_')"
  eval "l=\${M_opt_$1_$v:-}"
  if [ -z "$l" ]; then
    eval "l=\${M_lang_$v:-}"
  fi
  printf '%s' "${l:-$2}"
}

# ask_choice VAR KEY "values" — single choice; "*" in values allows free text
ask_choice() {
  var="$1"; key="$2"; values="$3"
  eval "current=\$$var"
  i=0
  for v in $values; do
    i=$((i + 1))
    if [ "$v" = "*" ]; then
      printf '   %2d) %s\n' "$i" "$(t other_free_text)"
    else
      mark=""
      [ "$v" = "$current" ] && mark="  $(t current_mark)"
      printf '   %2d) %s%s\n' "$i" "$(label_of "$key" "$v")" "$mark"
    fi
  done
  # show free-text current value if it's not one of the presets
  case " $values " in *" $current "*) ;; *) [ -n "$current" ] && printf '       %s %s\n' "$(t current_value)" "$current" ;; esac
  while :; do
    ask "   $(t choose_number) "
    a="$(trim "$REPLY")"
    [ -z "$a" ] && return 0
    case "$a" in *[!0-9]*) say invalid_number; continue ;; esac
    j=0; picked=""
    for v in $values; do j=$((j + 1)); [ "$j" -eq "$a" ] && picked="$v"; done
    if [ -z "$picked" ]; then say invalid_number; continue; fi
    if [ "$picked" = "*" ]; then
      ask "   $(t type_value) "
      free="$(trim "$REPLY")"
      [ -z "$free" ] && continue
      if ! safe_value "$free"; then say invalid_chars; continue; fi
      eval "$var=\$free"
    else
      eval "$var=\$picked"
    fi
    return 0
  done
}

# ask_multi VAR KEY "values" — multiple choice by numbers separated by spaces
ask_multi() {
  var="$1"; key="$2"; values="$3"
  eval "current=\$$var"
  i=0
  for v in $values; do
    i=$((i + 1))
    mark=""
    case " $current " in *" $v "*) mark="  $(t current_mark)" ;; esac
    printf '   %2d) %s%s\n' "$i" "$(label_of "$key" "$v")" "$mark"
  done
  while :; do
    ask "   $(t choose_numbers) "
    a="$(trim "$REPLY")"
    [ -z "$a" ] && return 0
    out=""; bad=0
    for n in $a; do
      case "$n" in *[!0-9]*) bad=1; break ;; esac
      j=0; picked=""
      for v in $values; do j=$((j + 1)); [ "$j" -eq "$n" ] && picked="$v"; done
      if [ -z "$picked" ]; then bad=1; break; fi
      case " $out " in *" $picked "*) ;; *) out="${out:+$out }$picked" ;; esac
    done
    if [ "$bad" -eq 1 ] || [ -z "$out" ]; then say invalid_number; continue; fi
    eval "$var=\$out"
    return 0
  done
}

normalize_path() {
  p="$(trim "$1")"
  case "$p" in
    \"*\") p="${p#\"}"; p="${p%\"}" ;;
    \'*\') p="${p#\'}"; p="${p%\'}" ;;
  esac
  p="$(printf '%s' "$p" | sed 's/\\\(.\)/\1/g')"
  case "$p" in
    "~") p="$HOME" ;;
    "~/"*) p="$HOME/${p#\~/}" ;;
  esac
  while [ "${#p}" -gt 1 ] && [ "${p%/}" != "$p" ]; do p="${p%/}"; done
  printf '%s' "$p"
}

ask_project_dirs() {
  if [ -n "$PROJECT_DIRS" ]; then
    shown=""
    old_ifs="$IFS"; IFS=":"
    for d in $PROJECT_DIRS; do shown="$shown  $(pretty "$d")"; done
    IFS="$old_ifs"
    printf '   %s%s\n' "$(t current_value)" "$shown"
    say keep_with_enter
  fi
  dirs=""; count=0
  while :; do
    ask "   $(t folder_n "$((count + 1))") "
    raw="$(trim "$REPLY")"
    if [ -z "$raw" ]; then
      if [ "$count" -eq 0 ] && [ -n "$PROJECT_DIRS" ]; then
        dirs=""
        old_ifs="$IFS"; IFS=":"
        for d in $PROJECT_DIRS; do e="$(to_config_path "$d")"; dirs="${dirs:+$dirs:}$e"; done
        IFS="$old_ifs"
        say kept
        break
      fi
      if [ "$count" -eq 0 ]; then
        ask "   $(t no_folder_skip) "
        case "$(trim "$REPLY")" in y|Y|yes|YES) say skipped_folders; break ;; *) continue ;; esac
      fi
      break
    fi
    path="$(normalize_path "$raw")"
    case "$path" in
      *\"*|*\`*|*\$*|*:*) say invalid_path_chars; continue ;;
      /*) ;;
      *) say need_full_path; continue ;;
    esac
    if [ ! -d "$path" ]; then
      ask "   $(t folder_missing_use "$(pretty "$path")") "
      case "$(trim "$REPLY")" in y|Y|yes|YES) ;; *) continue ;; esac
    fi
    e="$(to_config_path "$path")"
    case ":$dirs:" in *":$e:"*) say already_added; continue ;; esac
    dirs="${dirs:+$dirs:}$e"
    count=$((count + 1))
    say added "$(pretty "$path")"
  done
  PROJECT_DIRS="$dirs"
}

# ---------- questions ----------

header() { printf '\n%s\n' "$1"; [ -n "${2:-}" ] && printf '   %s\n' "$2"; return 0; }

say_title() { printf '%s\n' "== $(t configure_title)"; }

say_title
say config_files "$(pretty "$PROFILE_FILE")" "$(pretty "$MACHINE_FILE")"
[ -n "$LEGACY_LOADED" ] && say legacy_found "$(pretty "$LEGACY_CONFIG")"
printf '   %s\n' "$(t enter_keeps)"

if needs UI_LANG; then
  header "1. Language of this installer / 安装程序的语言"
  ask_choice UI_LANG UI_LANG "$OPT_UI_LANG_CHOICES"
  load_messages "$UI_LANG"
fi
if needs CONTENT_LANG; then
  header "2. $(t q_content_lang)" "$(t q_content_lang_hint)"
  ask_choice CONTENT_LANG CONTENT_LANG "$OPT_CONTENT_LANG_CHOICES"
fi
if needs REPLY_LANG; then
  header "3. $(t q_reply_lang)" "$(t q_reply_lang_hint)"
  ask_choice REPLY_LANG REPLY_LANG "$OPT_REPLY_LANG_CHOICES"
fi
if needs DOCS_LANG; then
  header "4. $(t q_docs_lang)" "$(t q_docs_lang_hint)"
  ask_choice DOCS_LANG DOCS_LANG "$OPT_DOCS_LANG_CHOICES"
fi
if needs WORK_MODE; then
  header "5. $(t q_work_mode)"
  ask_choice WORK_MODE WORK_MODE "$OPT_WORK_MODE_CHOICES"
fi
if needs DESIGN; then
  header "6. $(t q_design)"
  ask_choice DESIGN DESIGN "$OPT_DESIGN_CHOICES"
fi
if needs PLANNING; then
  header "7. $(t q_planning)"
  ask_choice PLANNING PLANNING "$OPT_PLANNING_CHOICES"
fi
if needs COMMITS; then
  header "8. $(t q_commits)"
  ask_choice COMMITS COMMITS "$OPT_COMMITS_CHOICES"
fi
if needs SCAFFOLD; then
  header "9. $(t q_scaffold)" "$(t q_scaffold_hint)"
  [ -n "$SCAFFOLD" ] && printf '   %s %s\n' "$(t current_value)" "$SCAFFOLD"
  while :; do
    ask "   > "
    a="$(trim "$REPLY")"
    [ -z "$a" ] && break
    if [ "$a" = "-" ]; then SCAFFOLD=""; break; fi
    if ! safe_value "$a"; then say invalid_chars; continue; fi
    SCAFFOLD="$a"; break
  done
fi
if needs STACKS; then
  header "10. $(t q_stacks)"
  ask_multi STACKS STACKS "$(repo_stacks | tr '\n' ' ')"
fi
if needs SKILLS; then
  header "11. $(t q_skills)" "$(t q_skills_hint)"
  printf '    1) %s\n    2) %s\n' "$(t skills_all)" "$(t skills_pick)"
  ask "   $(t choose_number) "
  case "$(trim "$REPLY")" in
    1) SKILLS="all" ;;
    2)
      [ "$SKILLS" = "all" ] && SKILLS="$(repo_skill_names | tr '\n' ' ' | sed 's/ $//')"
      ask_multi SKILLS SKILL "$(repo_skill_names | tr '\n' ' ')"
      ;;
  esac
fi
if needs TOOLS; then
  header "12. $(t q_tools)"
  ask_multi TOOLS TOOLS "$OPT_TOOLS_CHOICES"
fi
if needs PROJECT_DIRS; then
  header "13. $(t q_project_dirs)" "$(t q_project_dirs_hint)"
  ask_project_dirs
else
  # keep the machine value in config form
  dirs=""
  old_ifs="$IFS"; IFS=":"
  for d in $PROJECT_DIRS; do e="$(to_config_path "$d")"; dirs="${dirs:+$dirs:}$e"; done
  IFS="$old_ifs"
  PROJECT_DIRS="$dirs"
fi

write_profile
write_machine
if [ -n "$LEGACY_LOADED" ] && [ -f "$LEGACY_CONFIG" ]; then
  mkdir -p "$BACKUP_ROOT"
  mv "$LEGACY_CONFIG" "$BACKUP_ROOT/config.sh.migrated-$(date +%Y%m%d-%H%M%S)"
fi

echo
say saved_to "$(pretty "$PROFILE_FILE")"
grep -E '^[A-Z_]+=' "$PROFILE_FILE" | grep -v '^PROFILE_VERSION=' | sed 's/^/   /'
say saved_to "$(pretty "$MACHINE_FILE")"
grep -E '^[A-Z_]+=' "$MACHINE_FILE" | grep -v '^MACHINE_VERSION=' | sed 's/^/   /'
