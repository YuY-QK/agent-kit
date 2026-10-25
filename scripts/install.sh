#!/usr/bin/env bash
# Install or update agent-kit's global rules and skills for Claude Code and Codex.
#
# Usage:
#   scripts/install.sh                   install or update (symlinks by default)
#   scripts/install.sh --profile SOURCE  use a profile from a Git URL or a folder, then install
#   scripts/install.sh --configure       answer the settings questions again, then install
#   scripts/install.sh --dry-run         only show the install plan; change nothing
#   scripts/install.sh --review          open the web page even when there are no conflicts
#   scripts/install.sh --no-web          resolve conflicts in the terminal instead of the web page
#   scripts/install.sh --yes             don't ask: back up and replace conflicting files
#   scripts/install.sh --copy            copy files instead of symlinking
#   scripts/install.sh --uninstall       remove what agent-kit installed
#
# Before installing, the target locations are checked. Existing content that agent-kit
# didn't install is a conflict: keep it, replace it (after a backup) or merge it in the
# web page. Merge results are saved in your profile (overrides/), not in this repository.
# Without --yes, non-interactive runs always keep existing content.
#
# Compatible with bash 3.2.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/build.sh"

MODE="link"
DRY_RUN=0
RECONFIGURE=0
ASSUME_YES=0
USE_WEB=1
FORCE_REVIEW=0
PROFILE_SOURCE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE="copy" ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) MODE="uninstall" ;;
    --configure) RECONFIGURE=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-web) USE_WEB=0 ;;
    --review) FORCE_REVIEW=1 ;;
    --profile) shift; PROFILE_SOURCE="${1:-}"; [ -n "$PROFILE_SOURCE" ] || { echo "--profile needs a Git URL or a folder" >&2; exit 2; } ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agent-kit.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
PLAN="$WORK_DIR/plan.tsv"
DECISIONS="$WORK_DIR/decisions.tsv"
: > "$PLAN"
: > "$DECISIONS"
INSTALLED_DB="$STATE_DIR/installed.tsv"

load_settings
load_messages "$UI_LANG"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  [%s] %s\n' "$(t dry_run_tag)" "$*"
  else
    "$@"
  fi
}

# ---------- profile source ----------

if [ -n "$PROFILE_SOURCE" ] && [ "$MODE" != "uninstall" ]; then
  if is_git_url "$PROFILE_SOURCE"; then
    "$KIT_DIR/scripts/sync-profile.sh" clone "$PROFILE_SOURCE"
  else
    src="$PROFILE_SOURCE"
    case "$src" in "~/"*) src="$HOME/${src#\~/}" ;; esac
    if [ ! -d "$src" ]; then say profile_not_found "$PROFILE_SOURCE" >&2; exit 1; fi
    src="$(cd "$src" && pwd -P)"
    load_settings
    CUSTOM_PROFILE_DIR="$(to_config_path "$src")"
    dirs=""; old_ifs="$IFS"; IFS=":"
    for d in $PROJECT_DIRS; do dirs="${dirs:+$dirs:}$(to_config_path "$d")"; done
    IFS="$old_ifs"
    PROJECT_DIRS="$dirs"
    write_machine
    say profile_using "$(pretty "$src")"
  fi
  load_settings
  load_messages "$UI_LANG"
fi

# ---------- settings ----------

if [ "$MODE" != "uninstall" ] && [ "$DRY_RUN" -eq 0 ]; then
  if [ "$RECONFIGURE" -eq 1 ] || [ -n "$(echo $MISSING_KEYS)" ]; then
    if interactive; then
      first_run=0
      [ -f "$PROFILE_FILE" ] || first_run=1
      how="terminal"
      if [ "$USE_WEB" -eq 1 ] && web_available && { [ "$first_run" -eq 1 ] || [ "$RECONFIGURE" -eq 1 ]; }; then
        say configure_how
        printf '   1) %s\n   2) %s\n' "$(t configure_how_web)" "$(t configure_how_terminal)"
        printf '   %s ' "$(t choose_number)"
        read -r answer || answer=""
        [ "$answer" = "2" ] || how="web"
      fi
      if [ "$how" = "web" ]; then
        "$KIT_DIR/scripts/configure.sh" --web || { say configure_cancelled; exit 1; }
      elif [ "$RECONFIGURE" -eq 1 ] || [ "$first_run" -eq 1 ]; then
        "$KIT_DIR/scripts/configure.sh"
      else
        say configure_new_questions
        "$KIT_DIR/scripts/configure.sh" --missing
      fi
      echo
    else
      # non-interactive: keep what exists and fill the rest with defaults
      CUSTOM_PROFILE_DIR=""
      [ -n "${M_HAS_PROFILE_DIR:-}" ] && CUSTOM_PROFILE_DIR="$(to_config_path "$PROFILE_DIR")"
      dirs=""; old_ifs="$IFS"; IFS=":"
      for d in $PROJECT_DIRS; do dirs="${dirs:+$dirs:}$(to_config_path "$d")"; done
      IFS="$old_ifs"
      PROJECT_DIRS="$dirs"
      write_profile
      write_machine
      if [ -n "$LEGACY_LOADED" ] && [ -f "$LEGACY_CONFIG" ]; then
        mkdir -p "$BACKUP_ROOT"; mv "$LEGACY_CONFIG" "$BACKUP_ROOT/config.sh.migrated-$STAMP"
      fi
      say configure_defaults "$(pretty "$PROFILE_FILE")"
    fi
    load_settings
    load_messages "$UI_LANG"
  fi
fi

# A dry run builds into a temporary folder so nothing on disk changes.
REAL_BUILD_DIR="$BUILD_DIR"
if [ "$DRY_RUN" -eq 1 ]; then
  BUILD_DIR="$WORK_DIR/build"
fi

# ---------- helpers ----------

# Is this path a symlink that points into agent-kit's build folder or this repository?
points_to_us() {
  [ -L "$1" ] || return 1
  case "$(readlink "$1")" in
    "$REAL_BUILD_DIR"/*|"$REAL_BUILD_DIR"|"$KIT_DIR"/*|"$BUILD_DIR"/*) return 0 ;;
  esac
  return 1
}
is_kit_copy() {
  [ -d "$1" ] && [ ! -L "$1" ] && [ -f "$1/.agent-kit" ]
}
recorded_copy() {
  # a file we copied earlier and that nobody changed since
  [ -f "$1" ] && [ ! -L "$1" ] && [ -f "$INSTALLED_DB" ] || return 1
  h="$(hash_file "$1")"
  awk -F'\t' -v d="$1" -v h="$h" '$1 == d && $2 == h { found = 1 } END { exit !found }' "$INSTALLED_DB"
}
record_copy() {
  [ "$DRY_RUN" -eq 1 ] && return 0
  mkdir -p "$STATE_DIR"
  touch "$INSTALLED_DB"
  awk -F'\t' -v d="$1" '$1 != d' "$INSTALLED_DB" > "$INSTALLED_DB.tmp"
  printf '%s\t%s\n' "$1" "$(hash_file "$1")" >> "$INSTALLED_DB.tmp"
  mv "$INSTALLED_DB.tmp" "$INSTALLED_DB"
}
forget_copy() {
  [ -f "$INSTALLED_DB" ] || return 0
  awk -F'\t' -v d="$1" '$1 != d' "$INSTALLED_DB" > "$INSTALLED_DB.tmp" && mv "$INSTALLED_DB.tmp" "$INSTALLED_DB"
}

rules_path() {
  case "$1" in
    claude) printf '%s' "$HOME/.claude/CLAUDE.md" ;;
    codex) printf '%s' "$HOME/.codex/AGENTS.md" ;;
  esac
}
skills_path() {
  case "$1" in
    claude) printf '%s' "$HOME/.claude/skills" ;;
    codex) printf '%s' "$HOME/.agents/skills" ;;
  esac
}
main_file() {
  if [ -d "$1" ]; then printf '%s' "$1/SKILL.md"; else printf '%s' "$1"; fi
}

# new / uptodate / update / conflict
classify() {
  src="$1"; dest="$2"
  if points_to_us "$dest"; then
    if [ "$MODE" = "link" ] && [ "$(readlink "$dest")" = "$src" ]; then echo uptodate; else echo update; fi
  elif is_kit_copy "$dest"; then
    echo update
  elif recorded_copy "$dest"; then
    echo update
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && [ -f "$src" ] && cmp -s "$src" "$dest"; then
    if [ "$MODE" = "copy" ]; then echo uptodate; else echo update; fi
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && [ ! -s "$dest" ]; then
    echo update
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    echo conflict
  else
    echo new
  fi
}

add_plan() {
  # id kind tool name src dest status left right target base
  printf '0\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "$PLAN"
}

built_skills() {
  [ -f "$BUILD_DIR/skills.tsv" ] && cat "$BUILD_DIR/skills.tsv"
  return 0
}

build_plan() {
  gen="$BUILD_DIR/generated"
  for tool in $TOOLS; do
    case "$tool" in claude|codex) ;; *) say unknown_tool "$tool" >&2; continue ;; esac
    rd="$(rules_path "$tool")"
    left="-"; [ -e "$rd" ] && left="$(main_file "$rd")"
    add_plan rules "$tool" "$(basename "$rd")" "$BUILD_DIR/AGENTS.md" "$rd" \
      "$(classify "$BUILD_DIR/AGENTS.md" "$rd")" "$left" "$BUILD_DIR/AGENTS.md" \
      "$PROFILE_DIR/overrides/AGENTS.md" "$(hash_file "$gen/AGENTS.md")"
    sd="$(skills_path "$tool")"
    built_skills | while IFS="$(printf '\t')" read -r name origin dir; do
      dest="$sd/$name"
      left="-"; [ -e "$dest" ] && left="$(main_file "$dest")"
      target="$PROFILE_DIR/overrides/skills/$name/SKILL.md"
      base="$(hash_file "$gen/skills/$name/SKILL.md")"
      [ "$origin" = "profile" ] && { target="-"; base="-"; }
      add_plan skill "$tool" "$name" "$BUILD_DIR/skills/$name" "$dest" \
        "$(classify "$BUILD_DIR/skills/$name" "$dest")" \
        "$left" "$BUILD_DIR/skills/$name/SKILL.md" "$target" "$base"
    done
    # other skills in the folder that agent-kit didn't install and that don't share a name
    if [ -d "$sd" ]; then
      for entry in "$sd"/*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        name="$(basename "$entry")"
        points_to_us "$entry" && continue
        is_kit_copy "$entry" && continue
        [ -d "$entry" ] || continue
        if awk -F'\t' -v n="$name" '$1 == n { f = 1 } END { exit !f }' "$BUILD_DIR/skills.tsv" 2>/dev/null; then continue; fi
        if printf '%s\n' $(repo_skill_names) | grep -qx "$name"; then continue; fi
        add_plan foreign "$tool" "$name" "-" "$entry" foreign "$(main_file "$entry")" "-" "-" "-"
      done
    fi
  done

  # your overrides whose generated base has changed since you merged them
  ov="$PROFILE_DIR/overrides"
  if [ -f "$ov/AGENTS.md" ]; then
    cur="$(hash_file "$gen/AGENTS.md")"
    base="$(cat "$ov/AGENTS.md.base" 2>/dev/null || true)"
    if [ -z "$base" ]; then
      [ "$DRY_RUN" -eq 1 ] || printf '%s\n' "$cur" > "$ov/AGENTS.md.base"
    elif [ "$base" != "$cur" ]; then
      add_plan rules profile "AGENTS.md" "$gen/AGENTS.md" "$ov/AGENTS.md" outdated \
        "$ov/AGENTS.md" "$gen/AGENTS.md" "$ov/AGENTS.md" "$cur"
    fi
  fi
  if [ -d "$ov/skills" ]; then
    for f in "$ov"/skills/*/SKILL.md; do
      [ -f "$f" ] || continue
      name="$(basename "$(dirname "$f")")"
      g="$gen/skills/$name/SKILL.md"
      [ -f "$g" ] || continue
      cur="$(hash_file "$g")"
      base="$(cat "$f.base" 2>/dev/null || true)"
      if [ -z "$base" ]; then
        [ "$DRY_RUN" -eq 1 ] || printf '%s\n' "$cur" > "$f.base"
      elif [ "$base" != "$cur" ]; then
        add_plan skill profile "$name" "$g" "$f" outdated "$f" "$g" "$f" "$cur"
      fi
    done
  fi
  awk -F'\t' 'BEGIN { OFS = "\t" } { $1 = NR; print }' "$PLAN" > "$PLAN.tmp" && mv "$PLAN.tmp" "$PLAN"
}

count_status() {
  awk -F'\t' -v s="$1" '$7 == s' "$PLAN" | wc -l | tr -d ' '
}

print_table() {
  echo
  say plan_summary "$(count_status new)" "$(count_status update)" "$(count_status uptodate)" \
    "$(count_status conflict)" "$(count_status outdated)" "$(count_status foreign)"
  attention=$(( $(count_status conflict) + $(count_status outdated) + $(count_status foreign) ))
  if [ "$attention" -gt 0 ]; then
    echo
    printf '  %s\n' "$(t table_header)"
    echo "  ---- ------- ------------------------ ------------ ------------------------------"
    while IFS="$(printf '\t')" read -r id kind tool name src dest status left right target base; do
      case "$status" in conflict|outdated|foreign) ;; *) continue ;; esac
      printf '  %-4s %-7s %-24s %s %s\n' "$id" "$tool" "$name" "$(t "status_$status")" "$(pretty "$dest")"
    done < "$PLAN"
  fi
  echo
}

decide_in_web() {
  python3 "$KIT_DIR/scripts/lib/review_ui.py" \
    --plan "$PLAN" --decisions "$DECISIONS" --kit "$KIT_DIR" --home "$HOME" \
    --overrides "$PROFILE_DIR/overrides" --lang "$UI_LANG"
}

decide_in_terminal() {
  while IFS="$(printf '\t')" read -r id kind tool name src dest status left right target base; do
    case "$status" in conflict|outdated) ;; *) continue ;; esac
    while :; do
      printf '\n'
      if [ "$status" = "conflict" ]; then
        say terminal_conflict "$id" "$tool" "$name" "$(pretty "$dest")"
        printf '  %s ' "$(t terminal_conflict_choices)"
      else
        say terminal_outdated "$id" "$name" "$(pretty "$dest")"
        printf '  %s ' "$(t terminal_outdated_choices)"
      fi
      read -r answer < /dev/tty || answer="k"
      case "$answer" in
        r|R) printf '%s\treplace\n' "$id" >> "$DECISIONS"; break ;;
        k|K|"") printf '%s\tkeep\n' "$id" >> "$DECISIONS"; break ;;
        d|D)
          if [ -f "$left" ] && [ -f "$right" ]; then
            diff -u "$left" "$right" | sed "s#$HOME#~#g" | ${PAGER:-less} || true
          else
            say no_text_diff
          fi
          ;;
      esac
    done
  done < "$PLAN"
}

decision_for() {
  awk -F'\t' -v id="$1" '$1 == id { a = $2 } END { print a }' "$DECISIONS"
}

backup_item() {
  backup="$BACKUP_DIR/${1#"$HOME"/}"
  say backed_up "$(pretty "$1")" "$(pretty "$backup")"
  run mkdir -p "$(dirname "$backup")"
  run mv "$1" "$backup"
}

place() {
  src="$1"; dest="$2"
  run mkdir -p "$(dirname "$dest")"
  if points_to_us "$dest"; then
    if [ "$MODE" = "link" ] && [ "$(readlink "$dest")" = "$src" ]; then
      say up_to_date "$(pretty "$dest")"
      return
    fi
    run rm "$dest"
  elif is_kit_copy "$dest"; then
    run rm -rf "$dest"
  elif recorded_copy "$dest" || { [ -f "$dest" ] && [ ! -L "$dest" ] && [ -f "$src" ] && cmp -s "$src" "$dest"; }; then
    if [ "$MODE" = "copy" ] && [ -f "$src" ] && cmp -s "$src" "$dest"; then
      say up_to_date "$(pretty "$dest")"
      return
    fi
    run rm "$dest"
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && [ ! -s "$dest" ]; then
    backup_item "$dest"
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    backup_item "$dest"
  fi
  if [ "$MODE" = "link" ]; then
    run ln -s "$src" "$dest"
    forget_copy "$dest"
  else
    run cp -RL "$src" "$dest"
    if [ -d "$src" ]; then run touch "$dest/.agent-kit"; else record_copy "$dest"; fi
  fi
  say installed "$(pretty "$dest")"
}

prune_stale() {
  dir="$1"
  [ -d "$dir" ] || return 0
  for entry in "$dir"/*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    name="$(basename "$entry")"
    selected=0
    awk -F'\t' -v n="$name" '$1 == n { f = 1 } END { exit !f }' "$BUILD_DIR/skills.tsv" 2>/dev/null && selected=1
    if points_to_us "$entry" && { [ ! -e "$entry" ] || [ "$selected" -eq 0 ]; }; then
      say removed_stale "$(pretty "$entry")"
      run rm "$entry"
    elif is_kit_copy "$entry" && [ "$selected" -eq 0 ]; then
      say removed_stale "$(pretty "$entry")"
      run rm -rf "$entry"
    fi
  done
}

uninstall_all() {
  for tool in claude codex; do
    rd="$(rules_path "$tool")"; sd="$(skills_path "$tool")"
    printf '== %s\n' "$tool"
    if points_to_us "$rd" || recorded_copy "$rd"; then
      say removed "$(pretty "$rd")"; run rm "$rd"; forget_copy "$rd"
    fi
    [ -d "$sd" ] || continue
    for entry in "$sd"/*; do
      if points_to_us "$entry"; then say removed "$(pretty "$entry")"; run rm "$entry"
      elif is_kit_copy "$entry"; then say removed "$(pretty "$entry")"; run rm -rf "$entry"
      fi
    done
  done
  [ "$DRY_RUN" -eq 1 ] || rm -rf "$REAL_BUILD_DIR"
}

apply_override_decisions() {
  # outdated overrides: keep -> accept the new base; replace -> drop the override
  while IFS="$(printf '\t')" read -r id kind tool name src dest status left right target base; do
    [ "$status" = "outdated" ] || continue
    case "$(decision_for "$id")" in
      replace)
        backup_item "$dest"
        [ -f "$dest.base" ] && run rm "$dest.base"
        say override_dropped "$name"
        ;;
      merge)
        say override_merged "$name"
        ;;
      *)
        [ "$DRY_RUN" -eq 1 ] || printf '%s\n' "$base" > "$dest.base"
        say override_kept "$name"
        ;;
    esac
  done < "$PLAN"
}

apply_plan() {
  current_tool=""
  while IFS="$(printf '\t')" read -r id kind tool name src dest status left right target base; do
    [ "$tool" = "profile" ] && continue
    if [ "$tool" != "$current_tool" ]; then printf '== %s\n' "$tool"; current_tool="$tool"; fi
    case "$status" in
      new|update|uptodate) place "$src" "$dest" ;;
      conflict)
        case "$(decision_for "$id")" in
          replace|merge) place "$src" "$dest" ;;
          *) say kept_original "$(pretty "$dest")" "$name" ;;
        esac
        ;;
      foreign)
        if [ "$(decision_for "$id")" = "disable" ]; then backup_item "$dest"; say disabled "$name"; fi
        ;;
    esac
  done < "$PLAN"
  for tool in $TOOLS; do
    d="$(skills_path "$tool")"
    [ -n "$d" ] && prune_stale "$d"
  done
  return 0
}

# ---------- main ----------

say kit_location "$(pretty "$KIT_DIR")"
say summary_line "$TOOLS" "$STACKS" "$MODE" "$CONTENT_LANG"
say profile_location "$(pretty "$PROFILE_DIR")"

if [ "$MODE" = "uninstall" ]; then
  uninstall_all
  say done
  exit 0
fi

build_all
build_plan
print_table

if [ "$DRY_RUN" -eq 1 ]; then
  say dry_run_done
  exit 0
fi

conflicts=$(( $(count_status conflict) + $(count_status outdated) ))
foreigns="$(count_status foreign)"

if [ "$ASSUME_YES" -eq 1 ]; then
  awk -F'\t' '$7 == "conflict" { print $1 "\treplace" } $7 == "outdated" { print $1 "\tkeep" }' "$PLAN" > "$DECISIONS"
  [ "$(count_status outdated)" -gt 0 ] && say yes_keeps_overrides
elif [ "$conflicts" -gt 0 ] || [ "$FORCE_REVIEW" -eq 1 ]; then
  if ! interactive; then
    say noninteractive_keep
  elif [ "$USE_WEB" -eq 1 ] && web_available; then
    say opening_web
    if ! decide_in_web; then say cancelled; exit 1; fi
  else
    [ "$USE_WEB" -eq 1 ] && say no_python_terminal
    decide_in_terminal
  fi
elif [ "$foreigns" -gt 0 ]; then
  say foreign_hint
fi

apply_override_decisions
# overrides may have changed (merges, dropped overrides): rebuild before installing
build_all
apply_plan

if [ -d "$BACKUP_DIR" ]; then
  echo
  say backups_at "$(pretty "$BACKUP_DIR")"
fi
if command -v git >/dev/null 2>&1 && [ -d "$PROFILE_DIR/.git" ] && [ -n "$(git -C "$PROFILE_DIR" status --porcelain 2>/dev/null)" ]; then
  echo
  say profile_changed
  printf '  %s\n' "$(pretty "$KIT_DIR")/scripts/sync-profile.sh push"
elif [ ! -d "$PROFILE_DIR/.git" ]; then
  echo
  say profile_not_synced
fi
say done
