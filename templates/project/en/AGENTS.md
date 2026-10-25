# {{PROJECT_NAME}} AI working agreement

This file is the project-level entry point. It only defines this project's document routing, skills and commands. The shared way of working, priority of information and engineering baseline are in the global rules (installed in your home folder by agent-kit); concrete business rules, feature designs and technical choices live in the authoritative documents routed below and are not copied here.

## About this project

{{One sentence on what this project is and what stage it is at}}

## Document routing

Always read `docs/progress.md` first: current status, plan and open items. Then read only the material the task needs:

- Product scope, business rules, user flows and acceptance criteria: `docs/PRD_v1.0.md` and later decision records
- Screens and interaction prototype: `docs/PROTOTYPE_v1.0.md`
- Technical approach, module boundaries, data structures and interface contracts: `docs/TECH_DESIGN_v1.0.md`
- Approved key technical decisions: `docs/ADR_*.md`
- Plan, milestones, gates and risks: `docs/DEVELOPMENT_PLAN_v1.0.md`
- Project-specific development rules and constraints: `docs/AI_RULES.md`
- How it currently runs and its real structure: `README.md`, code, configuration and tests

Don't assume the content of documents that don't exist yet; create them with the `idea-to-plan` skill when needed.

## Skills

The shared skills are installed at user level: `idea-to-plan`, `product-change`, `ui-experience`, `architecture-change`, `change-review`, `quality-testing`, `orchestrate`, plus stack skills (`flutter-development` or `single-file-web`).

Skills specific to this project live in `.agents/skills/` (Codex) and `.claude/skills/` (Claude Code), and must not reuse the name of a shared skill:

- {{e.g. gameplay-system: core gameplay and randomness rules}}

## Subagents

When work is split across subagents, follow the `orchestrate` skill; the shared `task-worker` and `repo-scout` agents carry the general rules. Agents specific to this project live in `.claude/agents/`, use other names, and contain only what is specific to this project (which specification to read, which files they own, which checks to run):

- {{e.g. screen-builder: builds one screen following docs/TECH_DESIGN_v1.0.md}}

## Project commands

- Format: {{e.g. fvm dart format <files>}}
- Analyse: {{e.g. fvm flutter analyze}}
- Test: {{e.g. fvm flutter test}}
- Run: {{e.g. fvm flutter run}}
- Page or screen check (text output, instead of screenshots): {{e.g. node scripts/check-pages.cjs index.html}}
