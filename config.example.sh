# agent-kit 本机配置格式说明
#
# 不需要手动复制这个文件：运行 scripts/install.sh 时会在命令行里询问，
# 并生成 ~/.config/agent-kit/config.sh；以后想修改，运行 scripts/configure.sh。
# 本机配置只属于那台电脑，不要提交到仓库。

# 存放项目的目录，多个目录用冒号分隔，例如 "$HOME/Work/Projects:$HOME/Code"
PROJECT_DIRS=""

# 要安装到哪些工具：claude、codex，用空格分隔
AGENT_TOOLS="claude codex"

# 要安装哪些技术栈的技能：flutter、web，用空格分隔
STACKS="flutter web"
