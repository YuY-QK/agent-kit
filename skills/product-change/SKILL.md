---
name: product-change
description: Design or review product requirements, PRDs, feature scope, business rules, user flows and acceptance criteria, and control requirement changes. Use it to settle how the product should behave. For planning a brand-new idea from scratch use idea-to-plan; don't use this when only implementing already-confirmed requirements.
---

# Product change

Turn a product idea or change request into a product contract that is clearly bounded, implementable and verifiable, while keeping the current implementation and the target requirement apart.

## Establish the facts first

- Use the document routing in the project's `AGENTS.md` to find the PRD, prototype and project rules, and read only the sections relevant to this decision.
- When you need the current implementation or completion status, check it against code, tests and the development plan; read the prototype for screens and the release material for release scope.
- Don't present PRD targets as implemented, and don't turn existing placeholder behaviour into a product requirement.

## Define the product contract

As the task requires, make explicit:

- The problem, target users, scenarios and value.
- Current behaviour, target behaviour and the gap between them.
- In scope, out of scope and explicitly not doing.
- Preconditions, main flow, alternative flows and end conditions.
- Normal, empty, loading, failed, offline, disabled, permission-denied, cancelled and recovered states.
- Data ownership, entitlements, privacy, security and external dependencies.
- Acceptance criteria that can be observed through tests or manual checks.

When a request conflicts with the confirmed PRD, list the original rule, the proposed change, the reason, the affected scope and how acceptance changes, and let the user decide. Without the user's authorisation to change the product baseline, don't silently rewrite the PRD or implement the conflicting version.

## Keep the proposal sound

- Close one user value chain first; don't pull neighbouring ideas in with it.
- Don't create a sense of completion with placeholder entries, fake data, local success states or copy that can't be honoured.
- Don't write implementation details as product rules; include technical constraints only when they change the experience or the acceptance criteria.
- For irreversible, paid, deleting, uploading and long-running actions, define confirmation, cancellation, failure and recovery.
- Don't invent formal rules for undecided products, prices, payment channels or server behaviour.
- Each acceptance criterion describes only an observable result.

## Output

State the conclusion and its basis, and as the task requires cover: current vs target, scope and not-doing, key rules, states and edge cases, acceptance criteria, impact on UI/data/development/testing/docs, and open questions. For a small rule clarification, describe only what changes.

When the user only asked for product design, stop here and don't implement code. Write confirmed changes back into the PRD or a decision record.
