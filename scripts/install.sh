#!/usr/bin/env bash
# 把 agent-kit 的全局规则和技能安装到 Claude Code 和 Codex 读取的位置。
#
# 用法：
#   scripts/install.sh              安装或更新（默认使用软链接）
#   scripts/install.sh --copy       复制文件而不是软链接
#   scripts/install.sh --dry-run    只显示将要做的事，不改动任何文件
#   scripts/install.sh --uninstall  移除本工具装上的软链接
#
# 本机配置（可选）：~/.config/agent-kit/config.sh，示例见 config.example.sh
# 兼容 macOS 自带的 bash 3.2。

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
CONFIG_FILE="${AGENT_KIT_CONFIG:-$HOME/.config/agent-kit/config.sh}"

AGENT_TOOLS="claude codex"
STACKS="flutter web"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
fi

MODE="link"
DRY_RUN=0
for arg in ${1+"$@"}; do
  case "$arg" in
    --copy) MODE="copy" ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$HOME/.config/agent-kit/backups/$STAMP"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  [预演] $*"
  else
    "$@"
  fi
}

# 软链接是否指向本仓库内
points_into_kit() {
  [ -L "$1" ] || return 1
  case "$(readlink "$1")" in
    "$KIT_DIR"/*) return 0 ;;
    *) return 1 ;;
  esac
}

# 是否为 --copy 方式装上的目录（带标记文件）
is_kit_copy() {
  [ -d "$1" ] && [ ! -L "$1" ] && [ -f "$1/.agent-kit" ]
}

# 安装一个文件或目录到目标位置；已有的非本仓库内容先备份
place() {
  src="$1"
  dest="$2"
  run mkdir -p "$(dirname "$dest")"
  if points_into_kit "$dest"; then
    # 之前用软链接装的
    if [ "$MODE" = "link" ] && [ "$(readlink "$dest")" = "$src" ]; then
      echo "  已是最新：$dest"
      return
    fi
    run rm "$dest"
  elif is_kit_copy "$dest"; then
    # 之前用 --copy 装的目录
    run rm -rf "$dest"
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && cmp -s "$src" "$dest"; then
    # 内容和本仓库完全相同的文件
    if [ "$MODE" = "copy" ]; then
      echo "  已是最新：$dest"
      return
    fi
    run rm "$dest"
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    # 备份放到技能目录之外，避免被工具当成重复技能加载
    backup="$BACKUP_DIR/${dest#"$HOME"/}"
    echo "  备份已有内容：$dest -> $backup"
    run mkdir -p "$(dirname "$backup")"
    run mv "$dest" "$backup"
  fi
  if [ "$MODE" = "link" ]; then
    run ln -s "$src" "$dest"
  else
    run cp -R "$src" "$dest"
    if [ -d "$src" ]; then
      run touch "$dest/.agent-kit"
    fi
  fi
  echo "  已安装：$dest"
}

# 移除目标目录中指向本仓库、但源已不存在的软链接（技能被删除或改名时）
prune_stale() {
  dir="$1"
  [ -d "$dir" ] || return 0
  for entry in "$dir"/*; do
    [ -L "$entry" ] || continue
    if points_into_kit "$entry" && [ ! -e "$entry" ]; then
      echo "  移除失效链接：$entry"
      run rm "$entry"
    fi
  done
}

uninstall_dir() {
  dir="$1"
  [ -d "$dir" ] || return 0
  for entry in "$dir"/*; do
    if points_into_kit "$entry"; then
      echo "  移除：$entry"
      run rm "$entry"
    elif is_kit_copy "$entry"; then
      echo "  移除：$entry"
      run rm -rf "$entry"
    fi
  done
}

# 列出要安装的技能目录：通用技能 + 所选技术栈的技能
skill_dirs() {
  for d in "$KIT_DIR"/skills/*/; do
    [ -f "$d/SKILL.md" ] && echo "${d%/}"
  done
  for stack in $STACKS; do
    for d in "$KIT_DIR"/stacks/"$stack"/skills/*/; do
      [ -f "$d/SKILL.md" ] && echo "${d%/}"
    done
  done
  return 0
}

install_tool() {
  tool="$1"
  case "$tool" in
    claude)
      rules_dest="$HOME/.claude/CLAUDE.md"
      skills_dest="$HOME/.claude/skills"
      ;;
    codex)
      rules_dest="$HOME/.codex/AGENTS.md"
      skills_dest="$HOME/.agents/skills"
      ;;
    *)
      echo "跳过未知工具：$tool" >&2
      return
      ;;
  esac

  echo "== $tool"
  if [ "$MODE" = "uninstall" ]; then
    if points_into_kit "$rules_dest" || { [ -f "$rules_dest" ] && [ ! -L "$rules_dest" ] && cmp -s "$KIT_DIR/global/AGENTS.md" "$rules_dest"; }; then
      echo "  移除：$rules_dest"
      run rm "$rules_dest"
    fi
    uninstall_dir "$skills_dest"
    return
  fi

  place "$KIT_DIR/global/AGENTS.md" "$rules_dest"
  run mkdir -p "$skills_dest"
  skill_dirs | while IFS= read -r src; do
    place "$src" "$skills_dest/$(basename "$src")"
  done
  prune_stale "$skills_dest"
}

echo "agent-kit 位置：$KIT_DIR"
echo "工具：$AGENT_TOOLS    技术栈：$STACKS    方式：$MODE"
[ -f "$CONFIG_FILE" ] || echo "未找到本机配置 $CONFIG_FILE，使用默认值"

for tool in $AGENT_TOOLS; do
  install_tool "$tool"
done

echo "完成。"
