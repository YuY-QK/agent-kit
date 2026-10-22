#!/usr/bin/env bash
# 给一个项目放入 agent-kit 的项目模板：AGENTS.md、CLAUDE.md、docs/AI_RULES.md。
# 已存在的文件不会被覆盖。
#
# 用法：
#   scripts/new-project.sh <项目目录> [项目名称]
#
# 项目名称默认取目录名。生成后请填写 AGENTS.md 和 docs/AI_RULES.md 里 {{...}} 标出的部分。

set -eu

KIT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
TEMPLATE_DIR="$KIT_DIR/templates/project"

if [ $# -lt 1 ]; then
  sed -n '2,8p' "$0"
  exit 2
fi

PROJECT_DIR="$1"
if [ ! -d "$PROJECT_DIR" ]; then
  echo "目录不存在：$PROJECT_DIR" >&2
  exit 1
fi
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd -P)"
PROJECT_NAME="${2:-$(basename "$PROJECT_DIR")}"

# 替换模板中的项目名；名称里的 / & \ 先转义，避免破坏 sed 表达式
escaped_name="$(printf '%s' "$PROJECT_NAME" | sed 's/[\/&\\]/\\&/g')"

(cd "$TEMPLATE_DIR" && find . -type f) | while read -r rel; do
  rel="${rel#./}"
  dest="$PROJECT_DIR/$rel"
  if [ -e "$dest" ]; then
    echo "已存在，跳过：$rel"
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  sed "s/{{PROJECT_NAME}}/$escaped_name/g" "$TEMPLATE_DIR/$rel" > "$dest"
  echo "已创建：$rel"
done

echo "完成。请填写 AGENTS.md 和 docs/AI_RULES.md 中 {{...}} 标出的部分。"
