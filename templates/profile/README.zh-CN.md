# agent-kit 个人设置

[English](README.md)

这个仓库保存我在 [agent-kit](https://github.com/YuY-QK/agent-kit) 里的个人设置：助手使用的语言、我的工作方式、我自己的规则和技能，以及冲突合并的结果。agent-kit 会把它们和共享的规则、技能组合在一起，安装给 Claude Code 和 Codex。

这个仓库请保持**私有**。里面没有密码或本机路径，但写着你的工作方式。

## 目录

- [整体结构](#整体结构)
- [文件说明](#文件说明)
- [profile.sh 里的设置项](#profilesh-里的设置项)
- [修改设置](#修改设置)
- [自己的规则](#自己的规则)
- [自己的技能和子代理](#自己的技能和子代理)
- [冲突页面保存的覆盖文件](#冲突页面保存的覆盖文件)
- [在多台电脑间同步](#在多台电脑间同步)
- [云端会话](#云端会话)
- [不要放在这里的内容](#不要放在这里的内容)
- [常见问题](#常见问题)

## 整体结构

| 位置 | 内容 | 同步方式 |
|---|---|---|
| agent-kit 仓库（放在哪里都行） | 共享的规则、技能、子代理和脚本 | 公开仓库，`git pull` |
| `~/.config/agent-kit/profile/`（就是这个仓库） | 你的设置、规则、技能和覆盖文件 | 这个私有仓库 |
| `~/.config/agent-kit/machine.sh` | 只属于这台电脑：项目放在哪些目录 | 不同步 |
| `~/.claude/`、`~/.codex/`、`~/.agents/skills/` | 安装出来的结果 | 由 `scripts/install.sh` 生成 |

每次运行 `scripts/install.sh`，agent-kit 都会读取这份设置，生成全局规则和技能列表并安装。Claude Code 和 Codex 不会直接读这个仓库，所以这里改了任何东西，都要再运行一次 `scripts/install.sh`。

## 文件说明

| 路径 | 内容 |
|---|---|
| `profile.sh` | 你的偏好：语言、关于你、工作流程、技能、工具，详见下文 |
| `rules/*.md` | 你自己的规则，按文件名顺序加在全局规则末尾 |
| `skills/<名称>/SKILL.md` | 你自己的技能，和共享技能装在一起 |
| `agents/<名称>.md` | 你自己的 Claude Code 子代理（装到 `~/.claude/agents/`） |
| `overrides/` | 冲突页面保存的、你自己版本的共享文件，会替换生成的文件 |
| `README.md`、`README.zh-CN.md` | 本说明 |

还不存在的目录，直接新建即可。

## profile.sh 里的设置项

`profile.sh` 里只有 `KEY="value"` 这样的行；agent-kit 只读取这些值，不会执行这个文件。

| 设置项 | 可选值 | 含义 |
|---|---|---|
| `PROFILE_VERSION` | `1` | 格式版本，不要改 |
| `UI_LANG` | `en`、`zh-CN` | agent-kit 自己的终端提示和网页使用的语言 |
| `CONTENT_LANG` | `en`、`zh-CN` | 安装的规则和技能正文使用的语言 |
| `REPLY_LANG` | 语言代码（`en`、`zh-CN`、`ja` 等）或语言名称 | 助手回复你时使用的语言 |
| `DOCS_LANG` | `reply`，或语言代码、名称 | 文档、代码注释和提交说明使用的语言；`reply` 表示和 `REPLY_LANG` 相同 |
| `WORK_MODE` | `solo`、`team` | 独立开发还是团队协作，会影响协作规则 |
| `DESIGN` | `none`、`some` | 设计经验；选 `none` 时，助手会提出 2–3 个设计方向并说明理由，由你来选 |
| `PLANNING` | `full`、`light`、`off` | 动手前要做多少规划：完整文档、简短计划，或者不做 |
| `COMMITS` | `conventional`、`free` | 提交说明的格式（`feat: …`、`fix: …`，或自由书写） |
| `SCAFFOLD` | 自由文本，或留空 | 你自己的项目脚手架；新项目要从它开始时填写 |
| `STACKS` | 用空格分隔的技术栈名称（`flutter web`） | 安装哪些技术栈专用技能 |
| `SKILLS` | `all`，或用空格分隔的技能名称 | 安装哪些共享技能 |
| `TOOLS` | `claude`、`codex`，或两者 | 给哪些工具安装 |

`CONTENT_LANG` 和 `REPLY_LANG` 互不影响，例如规则正文用英文、回复用中文。

## 修改设置

最简单的是用 agent-kit 的设置页面或终端问答，它们会帮你检查取值：

```bash
cd <agent-kit 目录>
scripts/configure.sh --web     # 在浏览器里打开设置页面
scripts/configure.sh           # 或在终端里逐项回答
scripts/install.sh             # 按新设置安装
scripts/sync-profile.sh push   # 保存到这个仓库
```

`scripts/install.sh --configure` 可以一次完成提问和安装。也可以直接编辑 `profile.sh`，然后运行 `scripts/install.sh`。

## 自己的规则

适用于你所有项目的规则放在 `rules/` 里，每个主题一个 Markdown 文件。它们按文件名排序，加在共享规则之后，所以可以用数字前缀控制顺序：

```
rules/
  10-naming.md
  20-reviews.md
```

`rules/10-naming.md` 示例：

```markdown
## 命名

- 文件名使用 kebab-case。
- 面向用户的文字使用简体中文。
```

每个文件用 `##` 标题开头，这样能和全局规则衔接。只适用于某一个项目的规则不要放这里，写在那个项目的 `AGENTS.md` 或 `docs/AI_RULES.md` 里。

查看最终组合出来的规则：`scripts/build.sh --rules`。

## 自己的技能和子代理

- **技能**：新建 `skills/<名称>/SKILL.md`，写上开头信息（`name`、`description`）和具体说明；同一目录下的其他文件（脚本、模板）会一起安装。和共享技能同名时，会替换共享技能。
- **子代理**（Claude Code）：新建 `agents/<名称>.md`，使用 Claude Code 的子代理格式。和共享子代理同名时，会替换共享子代理。

然后运行 `scripts/install.sh`。如果只想小改某个共享技能，通常用下面的覆盖文件比整份复制更好。

## 冲突页面保存的覆盖文件

如果某个已安装的文件被你手动改过，而 agent-kit 的版本也变了，`scripts/install.sh` 会打开合并页面。你在那里保存的结果放在 `overrides/`：

| 路径 | 替换的内容 |
|---|---|
| `overrides/AGENTS.md` | 生成的全局规则 |
| `overrides/skills/<名称>/SKILL.md` | 某个共享技能 |
| `overrides/agents/<名称>.md` | 某个共享子代理 |

每个覆盖文件旁边都有一个 `.base` 文件，记录它基于 agent-kit 的哪个版本。agent-kit 之后再改动这个文件时，安装程序会把覆盖文件标记为过期，请你重新合并，所以你的修改不会被悄悄丢掉。

想放弃某个覆盖文件、回到 agent-kit 的版本，就删掉它和对应的 `.base`，再运行 `scripts/install.sh`。覆盖文件也可以直接手动编辑。

## 在多台电脑间同步

在这台电脑上，每次修改之后：

```bash
scripts/sync-profile.sh push "改了什么"
```

在另一台电脑上，第一次：

```bash
git clone git@github.com:YuY-QK/agent-kit.git
cd agent-kit
scripts/sync-profile.sh clone git@github.com:<you>/agent-profile.git
scripts/install.sh
```

之后要获取在别处做的修改：

```bash
scripts/sync-profile.sh pull
scripts/install.sh
```

`scripts/sync-profile.sh status` 会显示设置放在哪里、有没有还没保存的修改。设置有修改但还没推送时，`scripts/install.sh` 也会提醒你。安装时问的项目目录保存在 `machine.sh` 里，不在这里，所以每台电脑可以各自不同。

## 云端会话

网页版 Claude Code 的每个会话都从一个全新的容器开始。用 agent-kit 的 `start-project` 技能或 `scripts/enable-cloud.sh` 设置过的项目，会在那里自动安装 agent-kit。这些设置有两种方式带过去：

- **个人设置仓库**（`--profile repo`）：项目里只保存这个仓库的地址。云端会话要能读取这个私有仓库；读不到时会提示你，并改用默认设置。也可以在云端环境的变量里设置 `AGENT_KIT_PROFILE_REPO`。
- **复制到项目里**（`--profile copy` / `--with-profile`）：把 `profile.sh` 和 `rules/*.md` 复制到项目的 `.claude/agent-kit/` 并提交。这种方式一定能用，但能读这个项目的人也能读到这些设置，所以只用于私有项目。改了设置之后，要重新运行 `scripts/enable-cloud.sh <项目> --with-profile` 并提交。

## 不要放在这里的内容

- 密码、令牌、API 密钥等任何机密信息。
- 只在某一台电脑上存在的路径（放在 `machine.sh`，它不同步）。
- 某个项目专用的规则（写在那个项目里）。
- 没有改动过的共享技能副本（复制后就收不到 agent-kit 的更新了）。

## 常见问题

| 问题 | 解决办法 |
|---|---|
| 这里改了但没生效 | 运行 `scripts/install.sh`，然后新开一个会话；规则在会话启动时读取 |
| 另一台电脑还是旧设置 | 运行 `scripts/sync-profile.sh pull`，再运行 `scripts/install.sh` |
| `push` 被拒绝 | 另一台电脑先推送过：先运行 `scripts/sync-profile.sh pull`，再推送。如果 `pull` 因为两边都有修改而拒绝，运行 `git -C ~/.config/agent-kit/profile pull --rebase`，然后再推送 |
| `profile.sh` 里的值不对 | 运行 `scripts/configure.sh`，它会列出可选值 |
| 云端会话用的是英文默认设置 | 会话读不到这个仓库：给它访问权限，或者改用复制到项目里的方式 |
| 想从头再来 | 删掉 `profile.sh`，`scripts/install.sh` 会重新提问 |
