#!/usr/bin/env bash
# agent-kit SessionStart hook for Claude Code on the web.
#
# Cloud sessions start in a fresh container that has none of your global rules, skills
# or subagents. This hook installs them from agent-kit when a cloud session starts, then
# adds the global rules and the list of skills to the session's context.
# On your own computer it does nothing (agent-kit is installed there already).
#
# Added to a project by agent-kit's scripts/enable-cloud.sh. Settings (all optional):
#   AGENT_KIT_REPO          Git URL of agent-kit that the cloud can clone (public, HTTPS)
#   AGENT_KIT_PROFILE_REPO  Git URL of your profile repository, tried before the project's profile
#                           (default: the URL in .claude/agent-kit/profile-repo, if present)
#   AGENT_KIT_FORCE=1       run outside cloud sessions too (for testing)
# Profile used, in order: the profile repository, then a copied profile in .claude/agent-kit/,
# then agent-kit's defaults.
#
# It never fails the session: problems are reported in the context and in
# ~/.config/agent-kit/cloud-setup.log.

set -u
export GIT_TERMINAL_PROMPT=0   # never wait for a password

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || [ "${AGENT_KIT_FORCE:-}" = "1" ] || exit 0
cat >/dev/null 2>&1 || true   # the hook input (JSON) isn't needed

KIT_REPO="${AGENT_KIT_REPO:-__AGENT_KIT_REPO__}"
KIT_DIR="${AGENT_KIT_DIR:-$HOME/.agent-kit}"
CONFIG_HOME="${AGENT_KIT_HOME:-$HOME/.config/agent-kit}"
PROJECT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$CONFIG_HOME/cloud-setup.log"
STATE="$CONFIG_HOME/cloud-profile"
BUILD="$CONFIG_HOME/build"
PROFILE_REPO="${AGENT_KIT_PROFILE_REPO:-}"
if [ -z "$PROFILE_REPO" ] && [ -f "$PROJECT/.claude/agent-kit/profile-repo" ]; then
  PROFILE_REPO="$(head -1 "$PROJECT/.claude/agent-kit/profile-repo" | tr -d '[:space:]')"
fi

mkdir -p "$CONFIG_HOME"
problem=""
profile_from="agent-kit defaults"

if [ ! -f "$BUILD/AGENTS.md" ]; then
  (
    echo "== $(date) agent-kit cloud setup"
    if [ ! -d "$KIT_DIR/.git" ] && [ ! -f "$KIT_DIR/scripts/install.sh" ]; then
      git clone -q --depth 1 "$KIT_REPO" "$KIT_DIR" || exit 11
    fi
    if [ ! -f "$CONFIG_HOME/profile/profile.sh" ]; then
      : > "$STATE"
      if [ -n "$PROFILE_REPO" ]; then
        if git clone -q --depth 1 "$PROFILE_REPO" "$CONFIG_HOME/profile.tmp" 2>&1 &&
           [ -f "$CONFIG_HOME/profile.tmp/profile.sh" ]; then
          rm -rf "$CONFIG_HOME/profile"
          mv "$CONFIG_HOME/profile.tmp" "$CONFIG_HOME/profile"
          echo "from=$PROFILE_REPO" > "$STATE"
        else
          rm -rf "$CONFIG_HOME/profile.tmp"
          echo "failed=$PROFILE_REPO" > "$STATE"
        fi
      fi
      if [ ! -f "$CONFIG_HOME/profile/profile.sh" ] && [ -f "$PROJECT/.claude/agent-kit/profile.sh" ]; then
        rm -rf "$CONFIG_HOME/profile"
        cp -R "$PROJECT/.claude/agent-kit" "$CONFIG_HOME/profile"
        echo "from=the copy in .claude/agent-kit/" >> "$STATE"
      fi
    fi
    "$KIT_DIR/scripts/install.sh" --yes --no-web </dev/null || exit 12
  ) >>"$LOG" 2>&1
  case $? in
    0) ;;
    11) problem="could not clone agent-kit from $KIT_REPO (is the repository public, and is github.com allowed in this environment's network settings?)" ;;
    *) problem="agent-kit's install.sh failed" ;;
  esac
fi
profile_failed=""
if [ -f "$STATE" ]; then
  f="$(sed -n 's/^from=//p' "$STATE" | tail -1)"; [ -n "$f" ] && profile_from="$f"
  profile_failed="$(sed -n 's/^failed=//p' "$STATE" | tail -1)"
fi

# Build the context: the global rules plus where the skills and subagents are.
context_file="$CONFIG_HOME/cloud-context.md"
{
  if [ -n "$problem" ]; then
    echo "agent-kit could not set up this cloud session: $problem. Details: $LOG. Tell the user once, then continue without it."
  else
    echo "agent-kit installed the user's global rules, skills and subagents for this cloud session (profile: $profile_from)."
    if [ -n "$profile_failed" ]; then
      if [ "$profile_from" = "agent-kit defaults" ]; then
        echo "Could not clone the user's profile repository $profile_failed (this session probably has no access to it), so their own settings are not applied. Tell the user once: either give this environment access to that repository, or run agent-kit's scripts/enable-cloud.sh <project> --with-profile to copy the settings into the project (private projects only)."
      else
        echo "Could not clone the user's profile repository $profile_failed (this session probably has no access to it); used $profile_from instead, which may be older. Mention it to the user once."
      fi
    fi
    echo "The global rules follow. If they also appear above as ~/.claude/CLAUDE.md, it is the same text."
    echo
    cat "$BUILD/AGENTS.md"
    echo
    echo "## Installed skills"
    echo
    echo "If a skill below isn't offered as a skill in this session, read its SKILL.md when a task matches its description and follow it."
    echo
    if [ -f "$BUILD/skills.tsv" ]; then
      while IFS="$(printf '\t')" read -r name origin dir; do
        f="$HOME/.claude/skills/$name/SKILL.md"
        desc="$(sed -n 's/^description:[[:space:]]*//p' "$f" 2>/dev/null | head -1 | cut -c1-200)"
        echo "- \`$name\` (\`~/.claude/skills/$name/SKILL.md\`): $desc"
      done < "$BUILD/skills.tsv"
    fi
    if ls "$HOME"/.claude/agents/*.md >/dev/null 2>&1; then
      echo
      echo "## Installed subagents"
      echo
      echo "In \`~/.claude/agents/\`. If they can't be started by name in this session, put the brief's text (without its front matter) at the top of the subagent's task."
      echo
      for f in "$HOME"/.claude/agents/*.md; do
        echo "- \`$(basename "$f" .md)\`"
      done
    fi
  fi
} > "$context_file"

if command -v python3 >/dev/null 2>&1; then
  python3 -c '
import json, sys
text = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
' "$context_file"
else
  cat "$context_file"
fi
exit 0
