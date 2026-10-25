#!/usr/bin/env bash
# Generate the global rules and the skill folders from your profile.
# install.sh runs this automatically; run it yourself to preview.
#
# Usage:
#   scripts/build.sh                          build everything into ~/.config/agent-kit/build
#   scripts/build.sh --rules                  print the generated global rules (without overrides)
#   scripts/build.sh --rules --profile FILE   same, using another profile file (used by the web form)
#
# Compatible with bash 3.2.

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
# shellcheck disable=SC1091
. "$KIT_DIR/scripts/lib/common.sh"

# ---------- rules ----------

lang_name() {
  # $1: a language code (en, zh-CN, ...) or free text
  var="LANGNAME_$(printf '%s' "$1" | tr '-' '_')"
  case "$var" in *[!A-Za-z0-9_]*) printf '%s' "$1"; return ;; esac
  eval "name=\${$var:-}"
  if [ -n "$name" ]; then printf '%s' "$name"; else printf '%s' "$1"; fi
}

stacks_text() {
  out=""
  for s in $STACKS; do
    eval "label=\${STACK_$s:-$s}"
    if [ -z "$out" ]; then out="$label"; else out="$out$LIST_SEP$label"; fi
  done
  printf '%s' "$out"
}

# Replace {{NAME}} placeholders with values from the environment (no regex surprises).
fill_placeholders() {
  awk '
    BEGIN { n = split("REPLY_LANGUAGE DOCS_LANGUAGE STACKS_TEXT SCAFFOLD", keys, " ") }
    {
      line = $0
      for (k = 1; k <= n; k++) {
        tag = "{{" keys[k] "}}"; val = ENVIRON["AK_" keys[k]]
        out = ""
        while ((i = index(line, tag)) > 0) { out = out substr(line, 1, i - 1) val; line = substr(line, i + length(tag)) }
        line = out line
      }
      print line
    }'
}

# Print the generated global rules for the loaded profile.
# $1: profile folder (for personal rules in rules/*.md); may be empty.
build_rules() {
  profile_dir="$1"
  lang_dir="$KIT_DIR/rules/$CONTENT_LANG"
  [ -d "$lang_dir" ] || lang_dir="$KIT_DIR/rules/en"
  # shellcheck disable=SC1090
  . "$KIT_DIR/rules/en/labels.sh"
  # shellcheck disable=SC1090
  [ -f "$lang_dir/labels.sh" ] && . "$lang_dir/labels.sh"

  AK_REPLY_LANGUAGE="$(lang_name "$REPLY_LANG")"
  if [ "$DOCS_LANG" = "reply" ] || [ -z "$DOCS_LANG" ]; then
    AK_DOCS_LANGUAGE="$AK_REPLY_LANGUAGE"
  else
    AK_DOCS_LANGUAGE="$(lang_name "$DOCS_LANG")"
  fi
  AK_STACKS_TEXT="$(stacks_text)"
  AK_SCAFFOLD="$SCAFFOLD"
  export AK_REPLY_LANGUAGE AK_DOCS_LANGUAGE AK_STACKS_TEXT AK_SCAFFOLD

  while IFS= read -r entry || [ -n "$entry" ]; do
    case "$entry" in ''|'#'*) continue ;; esac
    path="${entry%% *}"
    cond=""
    case "$entry" in *' ?'*) cond="${entry##* ?}" ;; esac
    if [ -n "$cond" ]; then
      case "$cond" in *[!A-Z_]*) continue ;; esac
      eval "cval=\${$cond:-}"
      [ -n "$cval" ] || continue
    fi
    # expand ${VAR} with profile values (only simple upper-case names)
    while :; do
      case "$path" in
        *'${'*'}'*)
          pre="${path%%\$\{*}"; rest="${path#*\$\{}"; name="${rest%%\}*}"; post="${rest#*\}}"
          case "$name" in *[!A-Z_]*|'') break ;; esac
          eval "val=\${$name:-}"
          path="$pre$val$post"
          ;;
        *) break ;;
      esac
    done
    file="$lang_dir/$path"
    [ -f "$file" ] || file="$KIT_DIR/rules/en/$path"
    if [ ! -f "$file" ]; then
      echo "agent-kit: missing rule fragment: $path" >&2
      continue
    fi
    fill_placeholders < "$file"
  done < "$KIT_DIR/rules/manifest"

  # personal rules from the profile, in file-name order
  if [ -n "$profile_dir" ] && [ -d "$profile_dir/rules" ]; then
    for f in "$profile_dir"/rules/*.md; do
      [ -f "$f" ] || continue
      [ -s "$f" ] || continue
      printf '\n'
      cat "$f"
      # make sure the file ends with a newline
      [ -z "$(tail -c 1 "$f")" ] || printf '\n'
    done
  fi
}

# ---------- skills ----------

# List "name<TAB>source-folder" for every selected skill.
selected_skills() {
  for d in "$KIT_DIR"/skills/*/; do
    [ -f "$d/SKILL.md" ] || continue
    printf '%s\t%s\n' "$(basename "$d")" "${d%/}"
  done | filter_selected
  for s in $STACKS; do
    for d in "$KIT_DIR"/stacks/"$s"/skills/*/; do
      [ -f "$d/SKILL.md" ] || continue
      printf '%s\t%s\n' "$(basename "$d")" "${d%/}"
    done
  done | filter_selected
  return 0
}
filter_selected() {
  if [ "$SKILLS" = "all" ]; then cat; return; fi
  while IFS="$(printf '\t')" read -r name dir; do
    case " $SKILLS " in *" $name "*) printf '%s\t%s\n' "$name" "$dir" ;; esac
  done
}

# The SKILL.md variant for the content language (falls back to English).
skill_variant() {
  if [ -f "$1/SKILL.$CONTENT_LANG.md" ]; then echo "$1/SKILL.$CONTENT_LANG.md"; else echo "$1/SKILL.md"; fi
}

build_all() {
  gen="$BUILD_DIR/generated"
  rm -rf "$BUILD_DIR"
  mkdir -p "$gen/skills" "$BUILD_DIR/skills"

  build_rules "$PROFILE_DIR" > "$gen/AGENTS.md"
  if [ -f "$PROFILE_DIR/overrides/AGENTS.md" ]; then
    cp "$PROFILE_DIR/overrides/AGENTS.md" "$BUILD_DIR/AGENTS.md"
  else
    cp "$gen/AGENTS.md" "$BUILD_DIR/AGENTS.md"
  fi

  : > "$BUILD_DIR/skills.tsv"
  selected_skills | while IFS="$(printf '\t')" read -r name dir; do
    variant="$(skill_variant "$dir")"
    mkdir -p "$gen/skills/$name" "$BUILD_DIR/skills/$name"
    cp "$variant" "$gen/skills/$name/SKILL.md"
    if [ -f "$PROFILE_DIR/overrides/skills/$name/SKILL.md" ]; then
      cp "$PROFILE_DIR/overrides/skills/$name/SKILL.md" "$BUILD_DIR/skills/$name/SKILL.md"
    else
      ln -s "$variant" "$BUILD_DIR/skills/$name/SKILL.md"
    fi
    # other files in the skill folder (scripts, references) are linked as they are
    for f in "$dir"/* "$dir"/.[!.]*; do
      [ -e "$f" ] || continue
      base="$(basename "$f")"
      case "$base" in SKILL.md|SKILL.*.md) continue ;; esac
      ln -s "$f" "$BUILD_DIR/skills/$name/$base"
    done
    printf '%s\tkit\t%s\n' "$name" "$dir" >> "$BUILD_DIR/skills.tsv"
  done

  # your own skills from the profile; they win over a shared skill with the same name
  if [ -d "$PROFILE_DIR/skills" ]; then
    for d in "$PROFILE_DIR"/skills/*/; do
      [ -f "$d/SKILL.md" ] || continue
      name="$(basename "$d")"
      rm -rf "$BUILD_DIR/skills/$name" "$gen/skills/$name"
      ln -s "${d%/}" "$BUILD_DIR/skills/$name"
      awk -F'\t' -v n="$name" '$1 != n' "$BUILD_DIR/skills.tsv" > "$BUILD_DIR/skills.tsv.tmp"
      mv "$BUILD_DIR/skills.tsv.tmp" "$BUILD_DIR/skills.tsv"
      printf '%s\tprofile\t%s\n' "$name" "${d%/}" >> "$BUILD_DIR/skills.tsv"
    done
  fi
}

# ---------- main (when run directly) ----------

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  MODE="all"
  ALT_PROFILE=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --rules) MODE="rules" ;;
      --profile) shift; ALT_PROFILE="${1:-}" ;;
      -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
      *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
  done
  if [ -n "$ALT_PROFILE" ]; then
    AGENT_KIT_PROFILE_FILE="$ALT_PROFILE"
  fi
  load_settings
  if [ -n "${AGENT_KIT_PROFILE_FILE:-}" ]; then
    for k in $OPT_PROFILE_KEYS; do eval "P_$k=''; P_HAS_$k=''"; done
    read_kv_file "$AGENT_KIT_PROFILE_FILE" P
    UI_LANG="${P_UI_LANG:-$UI_LANG}"; CONTENT_LANG="${P_CONTENT_LANG:-$CONTENT_LANG}"
    REPLY_LANG="${P_REPLY_LANG:-$REPLY_LANG}"; DOCS_LANG="${P_DOCS_LANG:-$DOCS_LANG}"
    WORK_MODE="${P_WORK_MODE:-$WORK_MODE}"; DESIGN="${P_DESIGN:-$DESIGN}"
    PLANNING="${P_PLANNING:-$PLANNING}"; COMMITS="${P_COMMITS:-$COMMITS}"
    [ -n "$P_HAS_SCAFFOLD" ] && SCAFFOLD="$P_SCAFFOLD"
    [ -n "$P_HAS_STACKS" ] && STACKS="$P_STACKS"
    SKILLS="${P_SKILLS:-$SKILLS}"; TOOLS="${P_TOOLS:-$TOOLS}"
    [ -d "$KIT_DIR/rules/$CONTENT_LANG" ] || CONTENT_LANG=en
  fi
  if [ "$MODE" = "rules" ]; then
    build_rules "${AGENT_KIT_RULES_DIR:-$PROFILE_DIR}"
  else
    build_all
    echo "built: $(pretty "$BUILD_DIR")"
  fi
fi
