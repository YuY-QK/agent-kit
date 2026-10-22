# agent-kit

我的 AI 编程助手（Claude Code、Codex）规则与技能合集。全局统一，各项目再按需适配。

换一台电脑，克隆这个仓库并运行一次安装脚本，所有项目就能用上同一套规则和技能。只改一处，所有项目一起更新。

## 三层结构

| 层 | 内容 | 存放位置 |
|---|---|---|
| 全局层 | 个人习惯：中文交流、先计划后实施、信息优先级、文档约定、Git 与安全底线 | 本仓库 `global/` |
| 技术栈层 | 通用技能：想法到计划书、产品变更、界面体验、架构变更、代码审查、质量测试；按技术栈区分的开发规范 | 本仓库 `skills/`、`stacks/` |
| 项目层 | 文档路由、项目命令、业务规则、项目专属技能 | 各项目自己的仓库 |

本仓库只放前两层，不放任何具体项目的业务规则。

## 目录

```
agent-kit/
├── global/AGENTS.md          # 全局规则
├── skills/                   # 通用技能，每个技能一个目录，内含 SKILL.md
├── stacks/
│   ├── flutter/skills/       # Flutter 专用技能
│   └── web/skills/           # 单文件网页等 Web 专用技能
├── templates/project/        # 新项目起步文件：AGENTS.md、CLAUDE.md、docs/AI_RULES.md
├── scripts/
│   ├── install.sh            # 把全局规则和技能链接到各工具读取的位置
│   └── new-project.sh        # 给一个项目放入模板文件
└── config.example.sh         # 本机配置示例
```

## 在新电脑上安装

```sh
git clone https://github.com/YuY-QK/agent-kit.git   # 克隆到任意位置都可以
cd agent-kit
cp config.example.sh ~/.config/agent-kit/config.sh  # 按这台电脑的情况修改
./scripts/install.sh
```

安装脚本使用软链接，之后在任何一台电脑上 `git pull`，规则就会更新。

## 路径约定

仓库里不写死任何本机路径：

- 仓库自身的位置由脚本自动识别，克隆到哪里都可以。
- 用户目录统一写作 `$HOME`。
- 项目所在目录这类因电脑而异的设置，写在本机配置 `~/.config/agent-kit/config.sh` 里，不提交到仓库。
- 技能和规则里提到项目时只说“项目根目录”“`docs/`”，不写绝对路径。

## 在项目中使用

每个项目只保留项目层的内容：

- `AGENTS.md`：由模板生成，只填写本项目的文档路由和命令
- `CLAUDE.md`：只有一行 `@AGENTS.md`，让 Claude Code 和 Codex 读同一份规则
- `docs/`：PRD、原型、技术设计、开发计划等权威文档
- 本项目独有的技能（例如某个游戏的玩法规则）

## 许可证

[MIT](LICENSE)
