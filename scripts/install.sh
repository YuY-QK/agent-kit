#!/usr/bin/env bash
# 把 agent-kit 的全局规则和技能安装到 Claude Code 和 Codex 读取的位置。
#
# 用法：
#   scripts/install.sh              安装或更新（默认使用软链接）
#   scripts/install.sh --copy       复制文件而不是软链接
#   scripts/install.sh --dry-run    只列出安装计划，不改动任何文件
#   scripts/install.sh --review     即使没有冲突也打开网页，查看全部内容和其他来源的技能
#   scripts/install.sh --no-web     冲突在终端里逐个处理，不打开网页
#   scripts/install.sh --yes        不询问：冲突一律先备份再替换
#   scripts/install.sh --configure  先重新回答本机配置的问题，再安装
#   scripts/install.sh --uninstall  移除本工具装上的内容
#
# 安装前会先检查目标位置。已有的、不是 agent-kit 装的同名内容算作冲突，
# 由你决定替换（先备份）、保留原来的，或在网页里合并编辑。
# 非交互环境下（没有 --yes 时）冲突一律保留原内容。
#
# 本机配置：~/.config/agent-kit/config.sh。第一次运行时如果没有配置，
# 会在命令行里询问（见 scripts/configure.sh）。
# 兼容 macOS 自带的 bash 3.2。

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
CONFIG_FILE="${AGENT_KIT_CONFIG:-$HOME/.config/agent-kit/config.sh}"

MODE="link"
DRY_RUN=0
RECONFIGURE=0
ASSUME_YES=0
USE_WEB=1
FORCE_REVIEW=0
for arg in ${1+"$@"}; do
  case "$arg" in
    --copy) MODE="copy" ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) MODE="uninstall" ;;
    --configure) RECONFIGURE=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-web) USE_WEB=0 ;;
    --review) FORCE_REVIEW=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

interactive() {
  [ -t 0 ] || [ "${AGENT_KIT_PROMPT:-0}" = "1" ]
}

# 没有本机配置（或要求重新配置）时，在命令行里询问；预演和卸载不询问
if [ "$MODE" != "uninstall" ] && [ "$DRY_RUN" -eq 0 ]; then
  if [ "$RECONFIGURE" -eq 1 ] || [ ! -f "$CONFIG_FILE" ]; then
    if interactive; then
      "$KIT_DIR/scripts/configure.sh"
      echo
    else
      echo "未找到本机配置，且当前不是交互终端，跳过询问；以后可运行 scripts/configure.sh。" >&2
    fi
  fi
fi

AGENT_TOOLS="claude codex"
STACKS="flutter web"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$HOME/.config/agent-kit/backups/$STAMP"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agent-kit.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
PLAN="$WORK_DIR/plan.tsv"
DECISIONS="$WORK_DIR/decisions.tsv"
: > "$PLAN"
: > "$DECISIONS"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  [预演] $*"
  else
    "$@"
  fi
}

# 显示用：把 $HOME 开头的路径写成 ~
pretty() {
  case "$1" in
    "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;;
    *) printf '%s' "$1" ;;
  esac
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

# 各工具读取规则和技能的位置
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

# 所有 agent-kit 技能的名称（不论技术栈），用来识别同名冲突
all_kit_skill_names() {
  for f in "$KIT_DIR"/skills/*/SKILL.md "$KIT_DIR"/stacks/*/skills/*/SKILL.md; do
    [ -f "$f" ] && basename "$(dirname "$f")"
  done
  return 0
}

# 判断目标位置的状态：new 新增 / uptodate 已是最新 / update 更新 agent-kit 之前装的 / conflict 冲突
classify() {
  src="$1"
  dest="$2"
  if points_into_kit "$dest"; then
    if [ "$MODE" = "link" ] && [ "$(readlink "$dest")" = "$src" ]; then
      echo uptodate
    else
      echo update
    fi
  elif is_kit_copy "$dest"; then
    echo update
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && cmp -s "$src" "$dest"; then
    if [ "$MODE" = "copy" ]; then echo uptodate; else echo update; fi
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && [ ! -s "$dest" ]; then
    # 空文件，没有可保留的内容
    echo update
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    echo conflict
  else
    echo new
  fi
}

plan_id=0
add_plan() {
  # 字段：编号 类型 工具 名称 源 目标 状态
  plan_id=$((plan_id + 1))
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$plan_id" "$1" "$2" "$3" "$4" "$5" "$6" >> "$PLAN"
}

build_plan() {
  kit_names=" $(all_kit_skill_names | tr '\n' ' ') "
  for tool in $AGENT_TOOLS; do
    case "$tool" in
      claude|codex) ;;
      *) echo "跳过未知工具：$tool" >&2; continue ;;
    esac
    rules_dest="$(rules_path "$tool")"
    skills_dest="$(skills_path "$tool")"
    add_plan rules "$tool" "全局规则" "$KIT_DIR/global/AGENTS.md" "$rules_dest" \
      "$(classify "$KIT_DIR/global/AGENTS.md" "$rules_dest")"
    skill_dirs | while IFS= read -r src; do
      name="$(basename "$src")"
      dest="$skills_dest/$name"
      add_plan skill "$tool" "$name" "$src" "$dest" "$(classify "$src" "$dest")"
    done
    # 目标目录里其他来源的技能（不是 agent-kit 装的，也不同名）
    if [ -d "$skills_dest" ]; then
      for entry in "$skills_dest"/*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        name="$(basename "$entry")"
        points_into_kit "$entry" && continue
        is_kit_copy "$entry" && continue
        case "$kit_names" in *" $name "*) continue ;; esac
        [ -d "$entry" ] || continue
        add_plan foreign "$tool" "$name" "-" "$entry" foreign
      done
    fi
  done
  # 子 shell 里追加的编号不会传回来，按行重新编号
  awk -F'\t' 'BEGIN{OFS="\t"} {$1=NR; print}' "$PLAN" > "$PLAN.tmp" && mv "$PLAN.tmp" "$PLAN"
}

# 状态文字统一补成 4 个汉字宽（用全角空格），终端表格才能对齐
status_label() {
  case "$1" in
    new) echo "新增　　" ;;
    uptodate) echo "已是最新" ;;
    update) echo "更新　　" ;;
    conflict) echo "冲突　　" ;;
    foreign) echo "其他来源" ;;
  esac
}

count_status() {
  awk -F'\t' -v s="$1" '$7==s' "$PLAN" | wc -l | tr -d ' '
}

print_table() {
  # 表格：只列出需要关注的行（冲突、其他来源），其余汇总成数量
  echo
  printf '安装计划：新增 %s  更新 %s  已是最新 %s  冲突 %s  其他来源技能 %s\n' \
    "$(count_status new)" "$(count_status update)" "$(count_status uptodate)" \
    "$(count_status conflict)" "$(count_status foreign)"
  if [ "$(count_status conflict)" -gt 0 ] || [ "$(count_status foreign)" -gt 0 ]; then
    echo
    # 前三列只放英文和数字，宽度固定；表头按显示宽度手工对齐
    echo "  编号 工具    名称                     状态     位置"
    echo "  ---- ------- ------------------------ -------- ------------------------------"
    while IFS="$(printf '\t')" read -r id kind tool name src dest status; do
      case "$status" in conflict|foreign) ;; *) continue ;; esac
      label="$name"
      [ "$kind" = "rules" ] && label="$(basename "$dest")"
      printf '  %-4s %-7s %-24s %s %s\n' "$id" "$tool" "$label" "$(status_label "$status")" "$(pretty "$dest")"
    done < "$PLAN"
  fi
  echo
}

# 网页处理：需要 python3（macOS 装了 Xcode 命令行工具即自带）
web_available() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import http.server, difflib, json' >/dev/null 2>&1
}

decide_in_web() {
  python3 "$KIT_DIR/scripts/lib/review_ui.py" \
    --plan "$PLAN" --decisions "$DECISIONS" --kit "$KIT_DIR" --home "$HOME"
}

decide_in_terminal() {
  while IFS="$(printf '\t')" read -r id kind tool name src dest status; do
    [ "$status" = "conflict" ] || continue
    old="$dest"; new="$src"
    if [ -d "$dest" ]; then old="$dest/SKILL.md"; new="$src/SKILL.md"; fi
    while :; do
      printf '\n[%s] %s 的 %s 已存在：%s\n' "$id" "$tool" "$name" "$(pretty "$dest")"
      printf '  r = 替换（先备份旧的）  k = 保留我原来的  d = 查看差异 ：'
      read -r answer < /dev/tty || answer="k"
      case "$answer" in
        r|R) printf '%s\treplace\n' "$id" >> "$DECISIONS"; break ;;
        k|K|"") printf '%s\tkeep\n' "$id" >> "$DECISIONS"; break ;;
        d|D)
          if [ -f "$old" ]; then
            diff -u "$old" "$new" | sed "s#$HOME#~#g" | ${PAGER:-less} || true
          else
            echo "  旧内容不是普通文件，无法显示差异。"
          fi
          ;;
      esac
    done
  done < "$PLAN"
}

decision_for() {
  awk -F'\t' -v id="$1" '$1==id {a=$2} END {print a}' "$DECISIONS"
}

# 安装一个文件或目录到目标位置；已有的非本仓库内容先备份
place() {
  src="$1"
  dest="$2"
  run mkdir -p "$(dirname "$dest")"
  if points_into_kit "$dest"; then
    if [ "$MODE" = "link" ] && [ "$(readlink "$dest")" = "$src" ]; then
      echo "  已是最新：$(pretty "$dest")"
      return
    fi
    run rm "$dest"
  elif is_kit_copy "$dest"; then
    run rm -rf "$dest"
  elif [ -f "$dest" ] && [ ! -L "$dest" ] && cmp -s "$src" "$dest"; then
    if [ "$MODE" = "copy" ]; then
      echo "  已是最新：$(pretty "$dest")"
      return
    fi
    run rm "$dest"
  elif [ -e "$dest" ] || [ -L "$dest" ]; then
    backup_item "$dest"
  fi
  if [ "$MODE" = "link" ]; then
    run ln -s "$src" "$dest"
  else
    run cp -R "$src" "$dest"
    if [ -d "$src" ]; then
      run touch "$dest/.agent-kit"
    fi
  fi
  echo "  已安装：$(pretty "$dest")"
}

# 备份放到技能目录之外，避免被工具当成重复技能加载
backup_item() {
  backup="$BACKUP_DIR/${1#"$HOME"/}"
  echo "  备份：$(pretty "$1") -> $(pretty "$backup")"
  run mkdir -p "$(dirname "$backup")"
  run mv "$1" "$backup"
}

# 移除目标目录中指向本仓库、但源已不存在的软链接（技能被删除或改名时）
prune_stale() {
  dir="$1"
  [ -d "$dir" ] || return 0
  for entry in "$dir"/*; do
    [ -L "$entry" ] || continue
    if points_into_kit "$entry" && [ ! -e "$entry" ]; then
      echo "  移除失效链接：$(pretty "$entry")"
      run rm "$entry"
    fi
  done
}

uninstall_all() {
  for tool in $AGENT_TOOLS; do
    rules_dest="$(rules_path "$tool")"
    skills_dest="$(skills_path "$tool")"
    [ -n "$rules_dest" ] || continue
    echo "== $tool"
    if points_into_kit "$rules_dest" || { [ -f "$rules_dest" ] && [ ! -L "$rules_dest" ] && cmp -s "$KIT_DIR/global/AGENTS.md" "$rules_dest"; }; then
      echo "  移除：$(pretty "$rules_dest")"
      run rm "$rules_dest"
    fi
    [ -d "$skills_dest" ] || continue
    for entry in "$skills_dest"/*; do
      if points_into_kit "$entry"; then
        echo "  移除：$(pretty "$entry")"
        run rm "$entry"
      elif is_kit_copy "$entry"; then
        echo "  移除：$(pretty "$entry")"
        run rm -rf "$entry"
      fi
    done
  done
}

apply_plan() {
  current_tool=""
  while IFS="$(printf '\t')" read -r id kind tool name src dest status; do
    if [ "$tool" != "$current_tool" ]; then
      echo "== $tool"
      current_tool="$tool"
    fi
    case "$status" in
      new|update|uptodate)
        place "$src" "$dest"
        ;;
      conflict)
        case "$(decision_for "$id")" in
          replace) place "$src" "$dest" ;;
          *) echo "  保留原来的：$(pretty "$dest")（未安装 agent-kit 的 $name）" ;;
        esac
        ;;
      foreign)
        if [ "$(decision_for "$id")" = "disable" ]; then
          backup_item "$dest"
          echo "  已停用：$name"
        fi
        ;;
    esac
  done < "$PLAN"
  for tool in $AGENT_TOOLS; do
    d="$(skills_path "$tool")"
    [ -n "$d" ] && prune_stale "$d"
  done
  return 0
}

echo "agent-kit 位置：$(pretty "$KIT_DIR")"
echo "工具：$AGENT_TOOLS    技术栈：$STACKS    方式：$MODE"
[ -f "$CONFIG_FILE" ] || echo "未找到本机配置 $(pretty "$CONFIG_FILE")，使用默认值"

if [ "$MODE" = "uninstall" ]; then
  uninstall_all
  echo "完成。"
  exit 0
fi

build_plan
print_table

if [ "$DRY_RUN" -eq 1 ]; then
  echo "这是预演，没有改动任何文件。"
  exit 0
fi

conflicts="$(count_status conflict)"
foreigns="$(count_status foreign)"

if [ "$ASSUME_YES" -eq 1 ]; then
  awk -F'\t' '$7=="conflict" {print $1 "\treplace"}' "$PLAN" > "$DECISIONS"
elif [ "$conflicts" -gt 0 ] || [ "$FORCE_REVIEW" -eq 1 ]; then
  if ! interactive; then
    echo "当前不是交互终端：冲突一律保留原来的内容。想替换请加 --yes。"
  elif [ "$USE_WEB" -eq 1 ] && web_available; then
    echo "正在打开网页，请在浏览器里处理；处理完点“应用”，再回到这里。"
    if ! decide_in_web; then
      echo "已取消，没有改动任何文件。"
      exit 1
    fi
  else
    if [ "$USE_WEB" -eq 1 ]; then
      echo "没有找到可用的 python3，改为在终端里逐个处理。"
    fi
    decide_in_terminal
  fi
elif [ "$foreigns" -gt 0 ]; then
  echo "提示：上面列出的“其他来源”技能不是 agent-kit 装的，可能和通用技能功能重叠。"
  echo "      运行 scripts/install.sh --review 可以在网页里查看并决定是否停用。"
fi

apply_plan
if [ -d "$BACKUP_DIR" ]; then
  echo
  echo "被替换或停用的内容已备份到 $(pretty "$BACKUP_DIR")"
fi
# 网页里合并编辑会改动 agent-kit 仓库，提醒提交，其他电脑才能同步到
if command -v git >/dev/null 2>&1 && [ -d "$KIT_DIR/.git" ] && [ -n "$(git -C "$KIT_DIR" status --porcelain 2>/dev/null)" ]; then
  echo
  echo "agent-kit 仓库有未提交的修改（例如刚才合并编辑的内容）："
  git -C "$KIT_DIR" status --short | sed 's/^/  /'
  echo "确认无误后提交并推送，其他电脑 git pull 后就能用上："
  echo "  cd $(pretty "$KIT_DIR") && git add -A && git commit -m \"chore: 合并本机原有规则\" && git push"
fi
echo "完成。"
