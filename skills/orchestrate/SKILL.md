---
name: orchestrate
description: Run work across subagents as the main thread — choose models by difficulty, decide how many to run at once, write the tasks, merge the results and report once per stage. Use it when a task is split into delegated or parallel parts (batches of similar items, multi-module changes, inventories); don't use it for a small change you can simply do yourself.
---

# Orchestrate subagents

You are the main thread. You plan, decide, review and merge; subagents do bounded pieces of work. The goal is to finish with the least total usage without losing quality.

## Before starting

- Work from the plan in the project's progress summary (`docs/progress.md` unless the project's `AGENTS.md` names another file). Split only what the plan covers; confirm anything outside it with the user first.
- Write every task so it can be done without this conversation: the goal, the documents and files to read, the files it may change, the branch, the done-criteria, and the summary format (see the agent briefs below).
- Don't delegate what is quicker to do yourself, such as a few lines of change or a single lookup.

## Choose the model by difficulty

| Work | Who does it | Model tier (Claude Code) |
|---|---|---|
| Specifications, architecture decisions, final review | The main thread itself | Strongest (`opus`) |
| Implementing or migrating a bounded piece | `task-worker` subagent | Balanced (`sonnet`) |
| Read-only inventories, lookups, merging, running checks | `repo-scout` or `task-worker` | Fastest (`haiku`) or balanced |

- Never give a subagent the strongest tier. If a piece needs it, it is design work, and the main thread does it.
- In tools that can't choose a model per subagent, keep the same division of who does what.

## Usage

- Running several subagents at once doesn't change total usage. Usage is saved only by making each task cost less, keeping the main thread's context short, and matching the model to the difficulty.
- Choose how many to run at once only so that you don't hit a usage limit halfway through a task; normally one or two.
- If the remaining usage isn't enough to finish a task, don't start it: an interrupted task has to re-read its context when it resumes.
- Give one subagent at most two closely related items. More makes its context long and the quality drops.

## Merge and verify

- Read only the summary each subagent returns, not its full transcript.
- Requests to change shared files arrive in the summaries; decide and make those changes yourself, once, after reading all of them.
- After merging, run one quick local check. Leave the full test suite to CI when the project has CI.
- Do fact-checking (items marked "to verify") and content review once per batch, not inside every task.
- At the end of a stage, look at one or two screenshots of the result yourself if visual quality matters; subagents don't look at screenshots.

## Report and context

- Don't send progress messages in the middle of a stage. At the end of each stage, report once: what was done, how many subagents ran and with which models, verification results, and open items.
- Update the progress summary at the end of each stage. When the main conversation gets long, tell the user to start a new session; it continues from `AGENTS.md` and the summary.

## Agent briefs

The `agents/` folder next to this file holds the briefs that subagents follow. Each brief is the only place its rules are written.

- `task-worker` — implements one bounded task and returns a fixed-format summary.
- `repo-scout` — answers read-only questions about the code and documents.

In Claude Code, agent-kit installs these as user-level agents (`~/.claude/agents/`), so you can start them by name. In tools without agent definitions, include the text of the brief (without its front matter) at the top of the subagent's task.

A project can add its own agents with project-specific rules (for example in `.claude/agents/`). Give them different names, and put only what is specific to the project in them; the general rules stay in these briefs.
