# agent-kit

我的 AI 编程助手（Claude Code、Codex）规则与技能合集。全局统一，各项目再按需适配。

换一台电脑，克隆这个仓库并运行一次安装脚本，所有项目就能用上同一套规则和技能。只改一处，所有项目一起更新。

## 三层结构

| 层 | 内容 | 存放位置 |
|---|---|---|
| 全局层 | 个人习惯：中文交流、先计划后实施、信息优先级、文档约定、Git 与安全底线 | 本仓库 `global/` |
| 技术栈层 | 通用技能和按技术栈区分的开发规范 | 本仓库 `skills/`、`stacks/` |
| 项目层 | 文档路由、项目命令、业务规则、项目专属技能 | 各项目自己的仓库 |

本仓库只放前两层，不放任何具体项目的业务规则。优先级：当前任务的明确要求 > 项目层 > 全局层。

## 包含什么

**全局规则** `global/AGENTS.md`

**通用技能** `skills/`

| 技能 | 用途 |
|---|---|
| `idea-to-plan` | 新想法 → 想法简报、PRD、原型、技术设计、开发计划 |
| `product-change` | 需求、范围、业务规则、验收标准和需求变更 |
| `ui-experience` | 页面、交互、状态、响应式和可访问性 |
| `architecture-change` | 跨模块架构、数据与格式、外部集成、安全边界 |
| `change-review` | 代码审查与交付检查（默认只报告） |
| `quality-testing` | 测试策略、回归测试和质量证据 |

**技术栈技能** `stacks/`

| 技能 | 用途 |
|---|---|
| `flutter/flutter-development` | Flutter/Dart 实现、修复、重构 |
| `web/single-file-web` | 不依赖构建工具的单文件网页 |

**项目模板** `templates/project/`：`AGENTS.md`、`CLAUDE.md`、`docs/AI_RULES.md`

## 在新电脑上安装

```sh
gh repo clone YuY-QK/agent-kit ~/Work/agent-kit   # 克隆到任意位置都可以
cd ~/Work/agent-kit
./scripts/install.sh --dry-run                    # 可选：先预演，看看会改哪些文件
./scripts/install.sh
```

第一次运行 `install.sh` 时，会在命令行里依次询问：

1. 存放项目的目录：每次输入一个，可以把文件夹拖进终端或按 Tab 补全，输完直接回车
2. 要安装到哪些工具：`claude`、`codex`
3. 要安装哪些技术栈的技能：`flutter`、`web`

答案保存在这台电脑的 `~/.config/agent-kit/config.sh`。以后想修改，运行 `./scripts/configure.sh`（直接回车保留当前值），或 `./scripts/install.sh --configure` 改完顺便重新安装。

安装后的位置：

| 工具 | 全局规则 | 技能 |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/skills/` |
| Codex | `~/.codex/AGENTS.md` | `~/.agents/skills/` |

- 默认使用软链接，之后在任何一台电脑上 `git pull`，规则就会更新。
- 已有的同名文件不会被删除，会先备份到 `~/.config/agent-kit/backups/<时间>/`。
- 仓库里删除或改名的技能，再次运行安装时会自动清掉失效的链接。
- 某个工具不认软链接时，可以用 `./scripts/install.sh --copy` 改为复制（更新后要重新运行）。
- `./scripts/install.sh --uninstall` 移除本工具装上的内容，备份不受影响。

Claude App 和网页版里保存的技能存在 Claude 账号中，与这里是两套。以本仓库为准，修改技能后顺手更新账号里的那份。

## 在项目中使用

```sh
./scripts/new-project.sh <项目目录> [项目名称]   # 放入模板，已存在的文件不会覆盖
./scripts/check-projects.sh                     # 检查本机配置 PROJECT_DIRS 下的所有项目
./scripts/check-projects.sh <项目目录>...        # 只检查指定项目
```

每个项目只保留项目层的内容：

- `AGENTS.md`：只写本项目的文档路由、专属技能和命令
- `CLAUDE.md`：只有一行 `@AGENTS.md`，让 Claude Code 和 Codex 读同一份规则
- `docs/`：PRD、原型、技术设计、开发计划、`AI_RULES.md` 等权威文档
- 本项目独有的技能，放在 `.agents/skills/`（Codex）或 `.claude/skills/`（Claude Code），**名称不要与通用技能重复**：同名时两份都会出现，工具不知道该用哪一份

`check-projects.sh` 会指出缺少 `AGENTS.md`/`CLAUDE.md`、或与通用技能同名的项目技能副本。它只报告，不修改文件。

## 路径约定

仓库里不写死任何本机路径：

- 仓库自身的位置由脚本自动识别，克隆到哪里都可以。
- 用户目录统一写作 `$HOME`。
- 项目所在目录、要安装的工具和技术栈，安装时在命令行里输入，保存在本机配置 `~/.config/agent-kit/config.sh`，不提交到仓库。仓库里没有任何默认项目目录，格式说明见 `config.example.sh`。
- 技能和规则里提到项目时只说“项目根目录”“`docs/`”，不写绝对路径。

脚本兼容 macOS 自带的 bash 3.2。

## 许可证

[MIT](LICENSE)
