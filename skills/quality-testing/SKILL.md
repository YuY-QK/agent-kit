---
name: quality-testing
description: Design, write or review tests, regression scope and quality evidence — unit, component, integration, edge and failure cases. Use it for verification design and adding tests; don't use it when only implementing a feature with no verification design involved.
---

# Quality and testing

Use risk-driven tests to prove product behaviour, data safety and failure recovery, rather than chasing test counts or covering implementation details.

## Establish the basis

- Read the project rules and PRD acceptance criteria this verification needs; don't load unrelated product material for purely local tests.
- Confirm the current implementation from code and the target semantics from requirements; existing tests are not a source of truth above the product contract.
- From the change, identify user paths, data boundaries, platform boundaries and the failure points most likely to cause damage.
- When a requirement is unobservable or contradictory, raise it first; don't let tests make product decisions.

## Risk matrix

Cover what applies:

- Main flow, alternative flows and exit conditions.
- Minimum, maximum, empty, invalid and boundary-crossing values.
- Loading, empty, failure, retry, offline, permission denied and cancellation.
- Repeated taps, concurrency, idempotency, stale async results and lifecycle transitions.
- Data corruption, old versions, partial writes, full disks and recovery.
- Task-specific input sizes, state spaces and timing/ordering boundaries.
- Platform or plugin differences, and release-channel gates.

The higher the risk, the more important it is to prove that failures don't damage existing data — not just that the happy path returns the right result.

## Choose the test level

- Unit tests: pure models, algorithms, serialisation, state transitions, repository rules and error mapping.
- Component tests: user-visible states, interactions, navigation and accessibility semantics.
- Integration tests: databases, files, platform plugins and complete cross-layer flows.
- Manual verification: visuals, motion, performance, real devices and system interactions that automation can't judge reliably (background execution, system permissions). Mark these separately; they can't be inferred from simulators or unit tests.

Pick the cheapest level that proves the risk most directly.

## Writing tests

- Test names describe the condition and the observable result; each test checks one behavioural reason.
- Use deterministic inputs and controllable dependencies: fixed seeds for randomness, controllable clocks for time; no real network, random ordering or arbitrary waits.
- Probability or distribution tests use fixed samples and sensible tolerances, alongside rule-level tests.
- File and database tests use isolated temporary environments and clean up.
- Assert public behaviour, state and persisted results; don't lock in private functions or unrelated UI structure.
- A bug regression test must fail on the old implementation and pass after the fix.
- Never delete failing tests, weaken assertions or fabricate mock success to hide a problem.

## Running and reporting

Run the most relevant tests first, then widen to static analysis, the full suite and builds according to impact (using the project's commands). Report the commands actually run and their results, checks not run or blocked and why, and remaining risks; for complex or high-risk changes add a coverage matrix, the manual-check scope and follow-up gates.
