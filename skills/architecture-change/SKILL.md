---
name: architecture-change
description: Design or review cross-module architecture, dependency direction, databases, file formats, networking and integrations, long-running tasks, payments, permissions and security boundaries. Use it for structural changes; don't use it for local UI tweaks or simple function edits.
---

# Architecture and boundary changes

Give structural changes a design that can evolve, migrate, roll back and be verified — without over-engineering.

## Read the material

- Use the document routing in the project's `AGENTS.md` to find the technical design, ADRs and data or interface specifications, and read only the sections that affect this change.
- When interfaces, file formats, databases, permissions or release boundaries change, also read and maintain the matching contracts, migration notes and release checklists.
- When product scope or entitlements change, check the PRD; if there is no product document yet, ask the user to confirm the key contracts first.
- Documents describe the target; code and tests prove the current state. Don't mix them up.

## Define the boundaries first

Make explicit: the problem, constraints, non-goals and quality requirements; the authoritative data source, derived data, owners and lifecycle; module responsibilities, dependency direction, inputs/outputs and how failures propagate; sync/async, concurrency, cancellation, retries, idempotency and atomic commits; compatibility, migration, rollback, recovery and observability; and the impact of privacy, security, offline use and external-service failures.

## Design principles

- When there is a real trade-off, compare the current approach with at least one credible alternative; don't force a comparison for a small change with only one sensible option.
- Prefer a single source of truth, local changeability and clear boundaries; the number of layers or interfaces is not a measure of quality.
- The UI layer never talks to databases, files, HTTP, payment SDKs or secure storage directly.
- Core local functionality doesn't depend on the network; remote failures must not damage data already saved locally.
- Development mocks and real data sources are swapped behind the same repository/data-source boundary.
- Don't build general platforms, plugin systems or abstraction layers for features that haven't been approved.
- Designs that break data or protocol compatibility need explicit approval first, plus versioning, migration, rollback and tests.
- Record important decisions the user signs off on as ADRs.

## High-risk gates

Changes to databases, file formats, caches, backups, payments, licences, keys and platform permissions must cover: reading and upgrading old versions and upgrade failures; interruption, repeated runs and partial success; corrupted, forged, out-of-range, oversized input and full disks; staging-area validation, atomic commit and cleanup on failure; and redaction in logs.

Before integrating real payments, confirm the product and price source, the purchase state machine, receipt validation or the server boundary, restore purchases and idempotent fulfilment; until then, never implement a fake success.

## Output

Describe the background, constraints, current structure, options, recommended decision and its cost, modules and data flow, failure semantics, migration and rollback, testing strategy, documentation impact and open questions — only the parts relevant to this change. When the user only asked for a design or review, don't implement it.
