#!/usr/bin/env bash
# 在命令行里逐项询问，生成本机配置 ~/.config/agent-kit/config.sh。
# 每台电脑各自运行一次；之后想改，再运行一次即可（直接回车保留当前值）。
#
# 用法：
#   scripts/configure.sh
#
# 兼容 macOS 自带的 bash 3.2。

set -eu

CONFIG_FILE="${AGENT_KIT_CONFIG:-$HOME/.config/agent-kit/config.sh}"
ALL_TOOLS="claude codex"
ALL_STACKS="flutter web"

# 读取当前配置（如果有），作为重新配置时“直接回车保留”的值
PROJECT_DIRS=""
AGENT_TOOLS=""
STACKS=""
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
fi
OLD_PROJECT_DIRS="$PROJECT_DIRS"   # 读入时 $HOME 已展开成绝对路径
OLD_TOOLS="$AGENT_TOOLS"
OLD_STACKS="$STACKS"

# 从终端读一行；终端里启用行编辑，可以用 Tab 补全路径
ask() {
  prompt="$1"
  if [ -t 0 ]; then
    read -r -e -p "$prompt" REPLY || REPLY=""
  else
    printf '%s' "$prompt"
    read -r REPLY || REPLY=""
    echo
  fi
}

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

# 把用户输入的路径整理成绝对路径：去引号、处理拖入终端产生的反斜杠转义、展开 ~、去掉末尾 /
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

# 显示用：把 $HOME 开头的路径写成 ~
pretty() {
  case "$1" in
    "$HOME") printf '~' ;;
    "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# 写入配置用：把 $HOME 开头的路径写成 $HOME/...，换电脑用户名也能用
to_config() {
  case "$1" in
    "$HOME") printf '$HOME' ;;
    "$HOME"/*) printf '$HOME/%s' "${1#"$HOME"/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# 校验一组以空格分隔的选项都在允许范围内
valid_choices() {
  for item in $1; do
    ok=0
    for allowed in $2; do
      [ "$item" = "$allowed" ] && ok=1
    done
    [ "$ok" -eq 1 ] || return 1
  done
  return 0
}

echo "== agent-kit 本机配置"
echo "配置文件：$(pretty "$CONFIG_FILE")"
echo

# ---- 项目目录 ----
echo "1. 存放项目的目录"
echo "   检查脚本会把这些目录下的每个子文件夹当作一个项目。"
echo "   每次输入一个目录（可以把文件夹拖进终端，或按 Tab 补全），全部输完后直接回车。"
if [ -n "$OLD_PROJECT_DIRS" ]; then
  shown=""
  old_ifs="$IFS"; IFS=":"
  for d in $OLD_PROJECT_DIRS; do shown="$shown  $(pretty "$d")"; done
  IFS="$old_ifs"
  echo "   当前：$shown"
  echo "   第一项直接回车，表示保留当前设置。"
fi

dirs=""
count=0
while :; do
  ask "   目录 $((count + 1))："
  raw="$(trim "$REPLY")"
  if [ -z "$raw" ]; then
    if [ "$count" -eq 0 ] && [ -n "$OLD_PROJECT_DIRS" ]; then
      old_ifs="$IFS"; IFS=":"
      for d in $OLD_PROJECT_DIRS; do
        entry="$(to_config "$d")"
        if [ -z "$dirs" ]; then dirs="$entry"; else dirs="$dirs:$entry"; fi
      done
      IFS="$old_ifs"
      echo "   保留当前设置。"
      break
    fi
    if [ "$count" -eq 0 ]; then
      ask "   还没有输入任何目录。暂时不设置吗？[y/N] "
      case "$(trim "$REPLY")" in
        y|Y|yes|YES) echo "   暂不设置，以后可以重新运行 scripts/configure.sh。"; break ;;
        *) continue ;;
      esac
    fi
    break
  fi

  path="$(normalize_path "$raw")"
  case "$path" in
    *\"*|*\`*|*\$*|*:*)
      echo "   路径里不能包含 \" \` \$ 或 :，请换一个。"
      continue ;;
    /*) ;;
    *)
      echo "   请输入完整路径，例如 ~/Work/Projects。"
      continue ;;
  esac
  if [ ! -d "$path" ]; then
    ask "   $(pretty "$path") 不存在，仍然使用吗？[y/N] "
    case "$(trim "$REPLY")" in
      y|Y|yes|YES) ;;
      *) continue ;;
    esac
  fi
  entry="$(to_config "$path")"
  case ":$dirs:" in
    *":$entry:"*) echo "   已经添加过了。"; continue ;;
  esac
  if [ -z "$dirs" ]; then dirs="$entry"; else dirs="$dirs:$entry"; fi
  count=$((count + 1))
  echo "   已添加：$(pretty "$path")"
done
echo

# ---- 工具 ----
echo "2. 要安装到哪些工具（可选：$ALL_TOOLS，用空格分隔）"
current_tools="${OLD_TOOLS:-$ALL_TOOLS}"
while :; do
  ask "   直接回车使用 [$current_tools]："
  tools="$(trim "$REPLY")"
  [ -n "$tools" ] || tools="$current_tools"
  if valid_choices "$tools" "$ALL_TOOLS"; then break; fi
  echo "   只能填写：$ALL_TOOLS"
done
echo

# ---- 技术栈 ----
echo "3. 要安装哪些技术栈的技能（可选：$ALL_STACKS，用空格分隔）"
current_stacks="${OLD_STACKS:-$ALL_STACKS}"
while :; do
  ask "   直接回车使用 [$current_stacks]："
  stacks="$(trim "$REPLY")"
  [ -n "$stacks" ] || stacks="$current_stacks"
  if valid_choices "$stacks" "$ALL_STACKS"; then break; fi
  echo "   只能填写：$ALL_STACKS"
done
echo

mkdir -p "$(dirname "$CONFIG_FILE")"
{
  echo "# agent-kit 本机配置，由 scripts/configure.sh 生成。"
  echo "# 只属于这台电脑，不要提交到仓库。想修改可以重新运行 scripts/configure.sh。"
  echo
  echo "# 存放项目的目录，多个目录用冒号分隔"
  printf 'PROJECT_DIRS="%s"\n' "$dirs"
  echo
  echo "# 要安装到哪些工具：$ALL_TOOLS"
  printf 'AGENT_TOOLS="%s"\n' "$tools"
  echo
  echo "# 要安装哪些技术栈的技能：$ALL_STACKS"
  printf 'STACKS="%s"\n' "$stacks"
} > "$CONFIG_FILE"

echo "已保存到 $(pretty "$CONFIG_FILE")："
grep -E '^[A-Z_]+=' "$CONFIG_FILE" | sed 's/^/   /'
