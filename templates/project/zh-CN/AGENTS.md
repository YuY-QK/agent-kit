# {{PROJECT_NAME}} AI 协作约定

本文件是项目级入口，只定义本项目的文档路由、技能和命令。通用的协作方式、信息优先级和工程底线见全局规则（由 agent-kit 安装在用户目录）；具体业务规则、功能设计和技术方案写在下面路由到的权威文档里，不在本文件复制。

## 项目简介

{{一句话说明这个项目是什么、当前处于什么阶段}}

## 文档路由

如果有 `docs/HANDOFF.md`，最先读它：它写明上次会话停在哪里（内容合并进 `docs/progress.md` 后删掉）。开始工作前先读 `docs/progress.md`（现状、计划和待办），再按任务范围读取最少且必要的资料：

- 产品范围、业务规则、用户流程和验收标准：`docs/PRD_v1.0.md` 及后续决策记录
- 页面与交互原型：`docs/PROTOTYPE_v1.0.md`
- 技术方案、模块边界、数据结构和接口契约：`docs/TECH_DESIGN_v1.0.md`
- 已批准的重要技术决策：`docs/ADR_*.md`
- 计划、里程碑、门禁和风险：`docs/DEVELOPMENT_PLAN_v1.0.md`
- 项目专属的开发规则和约束：`docs/AI_RULES.md`
- 当前可运行方式和真实结构：`README.md`、代码、配置和测试

还没有建立的文档，不要假设它的内容；需要时用 `idea-to-plan` 技能补上。

## 技能

通用技能已安装在用户级目录：`idea-to-plan`、`product-change`、`ui-experience`、`architecture-change`、`change-review`、`quality-testing`、`orchestrate`，以及技术栈技能（`flutter-development` 或 `single-file-web`）。

本项目专属技能放在 `.agents/skills/`（Codex）和 `.claude/skills/`（Claude Code），名称不要与通用技能重复：

- {{例如 gameplay-system：核心玩法与随机规则}}

## 子线程

把工作拆给子线程时按 `orchestrate` 技能执行；通用的 `task-worker` 和 `repo-scout` 已包含通用规则。本项目专属的 agent 放在 `.claude/agents/`，名称不要与通用 agent 重复，里面只写本项目特有的内容（读哪份规格、负责哪些文件、跑哪些检查）：

- {{例如 screen-builder：按 docs/TECH_DESIGN_v1.0.md 完成一个页面}}

## 项目命令

- 格式化：{{例如 fvm dart format <files>}}
- 静态分析：{{例如 fvm flutter analyze}}
- 测试：{{例如 fvm flutter test}}
- 运行：{{例如 fvm flutter run}}
- 页面或界面检查（输出文字结论，代替截图）：{{例如 node scripts/check-pages.cjs index.html}}
