---
name: idea-to-plan
description: Turn a new app or product idea into a complete plan step by step — idea brief, product requirements document (PRD), prototype, technical design, development plan — then wire it into the project's AGENTS.md before implementation starts. Use this whenever the user says they have an idea, wants to build an app, tool or website, asks to flesh out an idea, or asks for a PRD, requirements, prototype/wireframes or a development plan, or wants to think a solution through before writing code — even if they never say "plan". Do not use it when the task is only implementing already-confirmed requirements or fixing a bug.
---

# Idea to plan

First refine the idea into a complete, coherent whole — a plan made of product documents and a prototype — and only then implement from that plan. This skill turns that habit into a repeatable process so every project has the same document structure and later implementation has something solid to follow.

Before starting, read “About me” in the global rules — solo or team, design experience, usual tech stacks, whether the user has their own scaffold — and adapt your questions and outputs to it.

## Principles

- **One stage at a time.** Stop after each stage and ask the user to confirm or change it before moving on. Writing every document in one go tends to compound unconfirmed assumptions.
- **Ask, don't invent.** Ask about anything the user hasn't made clear. What can't be settled yet goes into “Open questions” at the end of the document; don't decide it for the user.
- **Keep four states apart:** “current implementation”, “target requirement”, “proposal” and “unconfirmed assumption”. Label your suggestions as suggestions.
- **Complete but bounded.** Every document has a “Not doing” section. The smaller the first version, the sooner the idea gets validated. Say so directly when scope starts to creep.
- **Validate the biggest risk first.** If a core assumption is very uncertain (is the core loop fun, is it technically feasible), suggest a minimal prototype to test it before writing the full PRD.

## Step 0: decide where the documents live

- When working inside a project folder (its location may differ between computers — always use the currently open project root, never assume a fixed path), documents go in the project's `docs/` as Markdown, following the user's existing naming: `IDEA_BRIEF_v1.0.md`, `PRD_v1.0.md`, `PROTOTYPE_v1.0.md`, `TECH_DESIGN_v1.0.md`, `DEVELOPMENT_PLAN_v1.0.md`, `ADR_001_<topic>.md`.
- If there is no project folder yet, ask whether to create one. If the user only wants to talk it through first, work in the conversation or in whatever document tool the current environment offers, and move it into a project once the idea settles.
- If a document already exists, read it and build on it rather than starting a new one.

## Step 1: clarify the idea → idea brief

Act as a critical sparring partner. Ask 3–5 of the most important questions per round rather than a long list at once. Find out:

1. In one sentence: who it is for and what problem it solves
2. Target users and 2–3 core usage scenarios
3. The core loop: what the user does each time they open it, what they get, and why they come back
4. How it differs from existing products, and why it is worth building
5. What the smallest usable first version looks like
6. What is explicitly not being done
7. The biggest risk or least certain assumption, and the fastest way to validate it
8. Platform and technical leaning (mobile app, web, both) and whether it needs a backend, accounts or payments

Produce an **idea brief** (about one page):

```
# <Project> idea brief
## In one sentence
## Target users and core scenarios
## Core loop
## Difference and value
## First version scope
## Not doing
## Risks and how to validate them
## Open questions
```

**Gate:** write the PRD only after the user confirms the brief. If “Risks and how to validate them” shows major uncertainty, propose a minimal prototype first.

## Step 2: product requirements document (PRD)

Use this structure, matching the user's existing PRDs:

```
# <Project> product requirements
## 1. Document info (version, glossary, change log)
## 2. Positioning (one sentence, core value, product principles)
## 3. Goals and success criteria (what this version must achieve, how success is judged)
## 4. Users and core scenarios
## 5. Scope (included / not included / later candidates)
## 6. Core rules and core loop
## 7. Screens and interaction overview (screen list P00, P01…, how screens connect)
## 8. Requirements per screen (purpose, elements, interaction rules, states)
## 9. Data and content (what data is needed, where content comes from)
## 10. Errors and edge cases (empty, loading, failure, cancel, recovery)
## 11. Acceptance criteria (observable and verifiable)
## 12. Open questions
```

Write rules precisely enough to implement directly: what happens after a tap, when something counts as done, what happens on failure. Screen numbers are fixed from this step on; the prototype, technical design and development plan all use the same numbering.

PRDs get long. Write them in batches of chapters and show the user every few chapters.

## Step 3: prototype

If the global rules say the user has no design training, propose the visual direction yourself and let them choose; if they have design experience, follow their designs:

1. Offer 2–3 style directions (one sentence plus keywords each, e.g. “warm hand-drawn, rounded, soft colours”) and ask the user to pick one.
2. Write `PROTOTYPE_v1.0.md`: information architecture, screen list, a layout description per screen (what each area contains from top to bottom, what each control does and its states), and shared rules for dialogs and empty/loading/error states.
3. Make a prototype the user can look at: a single-file clickable HTML prototype in `docs/` (readable in light and dark mode, no horizontal scrolling at phone width), or a design canvas if the environment offers one and the user wants to edit it directly.
4. Once the visual direction is settled, you can capture colours, type, spacing and corner radii in `UI_DESIGN_SYSTEM_v1.0.md` for all later screens.

**Gate:** when the prototype and PRD disagree, point out the conflict, ask which one is right, then update the other.

## Step 4: technical design

Write `TECH_DESIGN_v1.0.md`:

```
# <Project> technical design
## 1. Purpose and scope
## 2. Quality attributes and non-functional goals (performance, offline, privacy, size…)
## 3. Overall architecture (technology choices and reasons, components, folder structure)
## 4. State and data model
## 5. Core logic and algorithms
## 6. Persistence, networking and integrations
## 7. Security and privacy
## 8. Testing strategy
## 9. Open questions
```

- If the global rules name the user's own scaffold, start new projects from it and follow its structure. Recommended layering for Flutter: screens/widgets → controller or use case → repository → data source or platform adapter.
- Single-file web projects: write business or algorithm logic as pure functions that don't touch the UI, separate from rendering, so they can move into an app later.
- For important decisions with several options (local storage choice, whether a backend is needed), compare them and recommend one; once the user decides, record it as an ADR.

## Step 5: development plan

Write `DEVELOPMENT_PLAN_v1.0.md`:

```
# <Project> development plan
## 1. Goals and boundaries (deliverables / explicitly excluded)
## 2. Milestones (M0 foundation, M1 core loop … finally stabilisation and release)
## 3. Tasks per milestone (tasks, outputs, done-criteria)
## 4. Required resources and missing inputs (images, audio, copy, accounts, backend… as one table)
## 5. Dependencies and gates
## 6. Testing and quality gates
## 7. Risks and mitigations
## 8. Requirements-to-milestone trace (which milestone covers each screen or rule in the PRD)
## 9. M0 kickoff checklist
```

M1 should get the core loop running as early as possible, even with a rough UI, to surface problems with the idea itself early.

## Step 6: wire it into the project and prepare to implement

1. Put an `AGENTS.md` at the project root, generated with agent-kit's `scripts/new-project.sh` (the template holds only the collaboration framework, no business rules); if agent-kit isn't installed, ask the user first. Fill in only the file paths in “Document routing”, the skill names and the project commands.
2. Add a `CLAUDE.md` containing the single line `@AGENTS.md`, so Claude Code and Codex read the same rules.
3. Fill in `docs/progress.md` (also from the template): the milestones from the development plan as the plan, “nothing built yet” as the status. It is the only progress summary; update it after each milestone.
4. List the M0 kickoff checklist and ask the user which item to start with.

## Light mode

A small tool or weekend project doesn't need five documents. When the user says “keep it simple” or the idea is small, combine everything into one **plan**: one sentence, scope and not-doing, screens and interactions, prototype (HTML), technical approach, development steps, open questions. Same process, shorter.

## Changing course

When requirements change during implementation, update the authoritative document first (requirements in the PRD, screens in the prototype, technical choices in the technical design or a new ADR), add a change-log entry, then change the code. Never change only the code and let the documents go stale.
