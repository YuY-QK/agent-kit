---
name: start-project
description: 用 agent-kit 一步搭好新项目的 GitHub 仓库：项目模板（AGENTS.md、CLAUDE.md、docs/AI_RULES.md、docs/progress.md）、对话里产出的计划文档、云端会话钩子和用户的个人设置，然后提交并推送。用户想开始、新建或搭建一个项目的仓库（通常是用 idea-to-plan 理清想法之后），并给出或准备给出 GitHub 地址时使用。已经搭好的项目加功能时不用。
---

# 开项目

把“这是 GitHub 地址”变成一个可以直接开发的仓库，在用户自己的电脑上和 Claude Code 云端会话里都能用。具体工作由 agent-kit 的 `scripts/bootstrap-project.sh` 完成；这个技能负责确认参数、根据计划填写模板并检查结果。

新建 GitHub 仓库这一步由用户来做（这里的工具不能创建仓库）。如果用户还没建，请他在 GitHub 上新建一个**空**仓库，把地址发给你。

## 1. 确认参数

一次问完，放在同一条消息里（有选择题工具时就用它），并给出默认值，让用户可以直接接受：

| 参数 | 默认值 | 说明 |
|---|---|---|
| 仓库 | 必填 | 任意形式：`git@github.com:owner/app.git`、https 地址或 `owner/app` |
| 项目名 | 仓库名 | 写进模板 |
| 语言 | 用户设置里的 `CONTENT_LANG` | `en` 或 `zh-CN` |
| 云端会话用的设置 | 私有项目 → `copy`；公开项目 → 有个人设置仓库时用 `repo`，否则 `none` | 见下文；要问清仓库是否私有 |
| 分支 | 空仓库用 `main`，否则用当前分支 | 仓库里已有内容时，可以提议用单独的分支 |
| 本地目录（仅在用户自己的电脑上） | `PROJECT_DIRS` 里的第一个目录，没有就用当前目录 | 克隆到哪里 |

设置的三种方式：

- `copy`：把用户的个人设置复制到 `.claude/agent-kit/` 并提交。云端会话一定能用上用户的语言和规则，但能读这个仓库的人也能读到这些设置，所以只用于私有项目。
- `repo`：把个人设置仓库的地址写进 `.claude/agent-kit/profile-repo`。不提交任何个人内容，但云端会话要有那个（通常是私有的）仓库的访问权限才能用；没有权限时，会话会提示并改用默认设置。
- `none`：云端会话使用 agent-kit 的默认设置（英文）。

## 2. 找到 agent-kit

按顺序用第一个可用的：

1. 安装这个技能的那份 agent-kit：解析这个 `SKILL.md` 的真实路径（`readlink -f` / `realpath`），往上两级就是 agent-kit（`<kit>/skills/start-project/SKILL.md`）。`<kit>/scripts/bootstrap-project.sh` 存在就用它。
2. `~/.agent-kit`（云端会话安装的位置），里面有 `scripts/bootstrap-project.sh` 就用它。
3. 克隆一份：`git clone --depth 1 https://github.com/YuY-QK/agent-kit ~/.agent-kit`。

都不行就停下，告诉用户连不上 agent-kit（通常是云端环境的网络设置）。

## 3. 获取仓库

- **在用户自己的电脑上**（能用 SSH 连 GitHub）：让脚本来克隆，传入地址和 `--dir <本地目录>/<名称>`。
- **在云端会话里**：那里用不了 SSH。如果会话已经检出了这个仓库（就是当前项目），直接用那个目录。否则用“给会话添加 GitHub 仓库”的工具，要求写权限，执行它返回的克隆命令，再把克隆出来的目录传给脚本。被拒绝时转告它给出的原因；通常是 Claude 的 GitHub App 没有这个新仓库的权限，需要用户在 GitHub 里把这个仓库加进 App 的访问范围（或允许所有仓库），然后再试一次。

## 4. 添加项目文件

```
<kit>/scripts/bootstrap-project.sh <地址或目录> [--dir <目录>] --name "<名称>" --lang <语言> --profile <copy|repo|none> [--branch <分支>]
```

不加 `--push` 时只准备文件。已有的文件不会被覆盖，所以仓库里已经有 README 或 License 也没关系，重复运行也是安全的。如果它提示 `AGENTS.md`、`CLAUDE.md` 或 `docs/` 里的文件已存在，就和 agent-kit 的模板（`<kit>/templates/project/<语言>/`）对比，向用户提出合并方案，不要直接保留或替换。

## 5. 放入计划

如果对话里已经产出了计划文档（例如用 `idea-to-plan` 写的想法简报、PRD、原型、技术设计、开发计划），以 Markdown 放进项目的 `docs/`，用项目模板路由到的文件名（`PRD_v1.0.md`、`PROTOTYPE_v1.0.md`、`TECH_DESIGN_v1.0.md`、`DEVELOPMENT_PLAN_v1.0.md`、`IDEA_BRIEF_v1.0.md`）。文档是 artifact 或在线文档的，读取内容后存成 Markdown。可点击的 HTML 原型直接放进 `docs/`。只保存实际产出并确认过的内容，不要补写还不存在的文档。

## 6. 填写模板

替换 `AGENTS.md` 和 `docs/AI_RULES.md` 里所有的 `{{...}}`，并填写 `docs/progress.md`：

- 内容取自计划：项目是什么、处于什么阶段、第一版范围和“不做”、约束、不变量、技术栈和命令、测试。
- 删掉用不上的示例行和路由（例如项目不用的技术栈技能、不存在的文档）。
- 计划里还没定的内容不要编：写明“待定”，在最后列给用户。
- `docs/progress.md`：计划部分写开发计划里的里程碑，现状写“尚未开始开发”。

检查有没有漏掉：`grep -rn '{{' AGENTS.md CLAUDE.md docs/` 应该没有输出。

## 7. 提交并推送

加上 `--push` 再运行一次同样的命令（用户想自定义提交说明时加 `--message "<说明>"`）。它会提交检出目录里的全部内容，并推送到选定的分支。推送失败就转告错误信息；在云端会话里通常是第 3 步的 GitHub 权限问题。

## 8. 汇报

简要告诉用户：

- 推送了什么，推到了哪个分支；
- 云端会话会用哪种设置（复制的设置、个人设置仓库或默认设置）；如果是公开仓库又用了 `copy`，说明这些设置现在是公开的；
- 第 6 步里待定的内容；
- 下一步：在这个仓库上**新开一个会话**进行开发。规则和技能在会话启动时加载，当前会话还没有它们。在新会话里问一句它用什么语言回复，就能确认设置已经生效。

以后用户改了设置、并且用的是 `copy`，要重新运行 `scripts/enable-cloud.sh <项目> --with-profile`，再提交 `.claude/`。
