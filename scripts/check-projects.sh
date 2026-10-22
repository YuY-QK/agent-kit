#!/usr/bin/env bash
# 检查各项目是否符合 agent-kit 的项目层约定，只报告，不修改任何文件。
#
# 检查项：
#   - 有没有 AGENTS.md
#   - 有没有 CLAUDE.md，且其中引用了 @AGENTS.md（Claude Code 才能读到同一份规则）
#   - 项目里有没有与通用技能同名的技能副本（会和用户级技能冲突，应删除或改名）
#
# 用法：
#   scripts/check-projects.sh              检查本机配置 PROJECT_DIRS 下的所有项目
#   scripts/check-projects.sh <项目目录>...  只检查指定项目

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
CONFIG_FILE="${AGENT_KIT_CONFIG:-$HOME/.config/agent-kit/config.sh}"
PROJECT_DIRS=""
STACKS="flutter web"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
fi

kit_skill_names() {
  for f in "$KIT_DIR"/skills/*/SKILL.md "$KIT_DIR"/stacks/*/skills/*/SKILL.md; do
    [ -f "$f" ] && basename "$(dirname "$f")"
  done
  return 0
}
KIT_SKILLS="$(kit_skill_names | tr '\n' ' ')"

is_kit_skill() {
  for s in $KIT_SKILLS; do
    [ "$s" = "$1" ] && return 0
  done
  return 1
}

check_project() {
  dir="$1"
  issues=""
  [ -f "$dir/AGENTS.md" ] || issues="$issues\n  - 缺少 AGENTS.md"
  if [ ! -f "$dir/CLAUDE.md" ]; then
    issues="$issues\n  - 缺少 CLAUDE.md（Claude Code 读不到 AGENTS.md）"
  elif [ -f "$dir/AGENTS.md" ] && ! grep -q '@AGENTS.md' "$dir/CLAUDE.md"; then
    issues="$issues\n  - CLAUDE.md 没有引用 @AGENTS.md，两份规则可能不一致"
  fi
  for skills_dir in "$dir/.agents/skills" "$dir/.claude/skills"; do
    [ -d "$skills_dir" ] || continue
    for s in "$skills_dir"/*/; do
      [ -d "$s" ] || continue
      name="$(basename "$s")"
      if is_kit_skill "$name"; then
        issues="$issues\n  - ${skills_dir#$dir/}/$name 与通用技能同名"
      fi
    done
  done
  if [ -z "$issues" ]; then
    echo "✓ $(basename "$dir")"
  else
    printf '✗ %s%b\n' "$(basename "$dir")" "$issues"
  fi
}

if [ $# -gt 0 ]; then
  for d in "$@"; do
    if [ -d "$d" ]; then
      check_project "$(cd "$d" && pwd -P)"
    else
      echo "目录不存在，跳过：$d" >&2
    fi
  done
  exit 0
fi

if [ -z "$PROJECT_DIRS" ]; then
  echo "本机配置里没有 PROJECT_DIRS，请在 $CONFIG_FILE 中设置，或直接传入项目目录。" >&2
  exit 2
fi

# PROJECT_DIRS 用空格分隔；单个目录路径里不要含空格
for root in $PROJECT_DIRS; do
  [ -d "$root" ] || { echo "目录不存在，跳过：$root" >&2; continue; }
  for d in "$root"/*/; do
    d="${d%/}"
    # 只检查看起来是项目的目录
    if [ -d "$d/.git" ] || [ -f "$d/AGENTS.md" ] || [ -f "$d/CLAUDE.md" ]; then
      check_project "$d"
    fi
  done
done
