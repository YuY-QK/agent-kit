---
name: start-project
description: Set up a new project's GitHub repository in one go with agent-kit — project template (AGENTS.md, CLAUDE.md, docs/AI_RULES.md, docs/progress.md), the plan documents from the conversation, the cloud-session hook and the user's settings — then commit and push. Use when the user wants to start, create, open or set up the repository for a project (often right after shaping an idea with idea-to-plan) and gives, or is about to give, a GitHub address. Not for adding features to a project that is already set up.
---

# Start a project

Turn "here is the GitHub address" into a repository that is ready for development, both on the user's computer and in Claude Code cloud sessions. The work is done by agent-kit's `scripts/bootstrap-project.sh`; this skill gathers the parameters, fills in the templates from the plan and checks the result.

Creating the GitHub repository itself is the user's step (the tools here can't create repositories). If they haven't made one yet, ask them to create an **empty** repository on GitHub and give you its address.

## 1. Confirm the parameters

Ask once, in a single message (use the multiple-choice question tool when it is available), and offer the defaults so the user can just accept them:

| Parameter | Default | Notes |
|---|---|---|
| Repository | required | Any form: `git@github.com:owner/app.git`, an https URL or `owner/app` |
| Project name | the repository name | Written into the templates |
| Language | `CONTENT_LANG` from the user's settings | `en` or `zh-CN` |
| Settings for cloud sessions | private project → `copy`; public project → `repo` if the user has a profile repository, otherwise `none` | See below; ask whether the repository is private |
| Branch | `main` for an empty repository, otherwise the current branch | Offer a separate branch if the repository already has content |
| Local folder (on the user's computer only) | the first folder in `PROJECT_DIRS`, otherwise the current folder | Where to clone |

Settings modes:

- `copy`: copies the user's profile into `.claude/agent-kit/` and commits it. Cloud sessions always get the user's languages and rules, but anyone who can read the repository can read the profile, so only for private projects.
- `repo`: writes the profile repository's URL into `.claude/agent-kit/profile-repo`. Nothing personal is committed, but a cloud session can only use it if it has access to that (usually private) repository; if not, the session says so and uses the defaults.
- `none`: cloud sessions use agent-kit's defaults (English).

## 2. Find agent-kit

Use the first that works:

1. The checkout this skill is installed from: resolve the real path of this `SKILL.md` (`readlink -f` / `realpath`); agent-kit is two folders up (`<kit>/skills/start-project/SKILL.md`). Use it if `<kit>/scripts/bootstrap-project.sh` exists.
2. `~/.agent-kit` (where cloud sessions install it), if `scripts/bootstrap-project.sh` exists there.
3. Clone it: `git clone --depth 1 https://github.com/YuY-QK/agent-kit ~/.agent-kit`.

If none works, stop and tell the user agent-kit couldn't be reached (usually the network settings of a cloud environment).

**Make sure the user's settings are on this machine**: `copy` and `repo` both use the user's profile. If `~/.config/agent-kit/profile/profile.sh` is missing, or that folder isn't the user's own profile repository (`git -C ~/.config/agent-kit/profile remote get-url origin` prints nothing), only the defaults are here (typical in a fresh cloud session). Ask for the user's profile repository; in a cloud session first get read access with the tool that adds a repository, then run `<kit>/scripts/sync-profile.sh clone <url>` (in the cloud, the https URL that tool gives) and `<kit>/scripts/install.sh --yes --no-web`. If the user has no profile repository, tell them `copy` would only copy the defaults and suggest `none` for now, to be filled in later from their own computer.

## 3. Get the repository

- **On the user's computer** (SSH to GitHub works): let the script clone it, passing the address and `--dir <local folder>/<name>`.
- **In a cloud session**: SSH isn't available there. If the session already has this repository checked out (the current project), use that folder. Otherwise use the tool that adds a GitHub repository to the session, with push access, and run the clone command it returns; then pass the cloned folder to the script. If access is refused, relay the reason it gives; usually the Claude GitHub App isn't allowed to use the new repository, and the user has to add the repository to the app's access in GitHub (or allow all repositories), then ask again.

## 4. Add the project files

```
<kit>/scripts/bootstrap-project.sh <address or folder> [--dir <folder>] --name "<name>" --lang <lang> --profile <copy|repo|none> [--branch <branch>]
```

Without `--push` it only prepares the files. Existing files are never overwritten, so a repository that already has a README or license is fine, and running it again is safe. If it reports `AGENTS.md`, `CLAUDE.md` or a `docs/` file as already there, compare it with agent-kit's template (`<kit>/templates/project/<lang>/`) and propose to the user how to merge them instead of silently keeping or replacing it.

## 5. Bring in the plan

If the conversation produced plan documents (for example with `idea-to-plan`: idea brief, PRD, prototype, technical design, development plan), put them in the project's `docs/` as Markdown, using the names the project template routes to (`PRD_v1.0.md`, `PROTOTYPE_v1.0.md`, `TECH_DESIGN_v1.0.md`, `DEVELOPMENT_PLAN_v1.0.md`, `IDEA_BRIEF_v1.0.md`). A document that lives as an artifact or doc: read it and save its content as Markdown. A clickable HTML prototype goes in `docs/` as it is. Only save what was actually produced and confirmed; don't write documents that don't exist yet.

## 6. Fill in the templates

Replace every `{{...}}` in `AGENTS.md` and `docs/AI_RULES.md`, and fill in `docs/progress.md`:

- Take the content from the plan: what the project is and its stage, the first version's scope and "not doing", constraints, invariants, tech stack and commands, tests.
- Delete example lines and routes that don't apply (for example the stack skill the project doesn't use, or documents that don't exist).
- Where the plan doesn't settle something, don't invent it: write that it is still open (in the template's language) and list it for the user at the end.
- `docs/progress.md`: the milestones from the development plan as the plan, "nothing built yet" as the status.

Check that nothing was missed: `grep -rn '{{' AGENTS.md CLAUDE.md docs/` should print nothing.

## 7. Commit and push

Run the same command again with `--push` (and `--message "<message>"` if the user wants their own). It commits everything in the checkout and pushes to the chosen branch. If the push fails, report the message; in a cloud session it is usually the GitHub access from step 3.

## 8. Report

Tell the user briefly:

- what was pushed, and to which branch;
- which settings cloud sessions will use (copied profile, profile repository, or defaults), and for `copy` in a public repository, that the profile is now public;
- the open points from step 6;
- next step: start a **new** session on this repository to develop — the rules and skills are loaded when a session starts, so this session doesn't have them yet. Asking the new session which language it replies in is a quick check that the settings arrived.

If the user changes their settings later and used `copy`, they rerun `scripts/enable-cloud.sh <project> --with-profile` and commit `.claude/` again.
