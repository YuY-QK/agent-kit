---
name: change-review
description: Review code, test or documentation changes for problems in product semantics, correctness, data safety, architecture, privacy and regressions. Use it for code review and pre-delivery checks; it reports by default and doesn't edit. Don't use it when the user has asked you to implement the change directly.
---

# Change review

The goal is to find real defects and delivery risks, not to fill the report with style preferences. Report by default; fix only when the user explicitly asks.

## Set the scope

- Read the project rules, PRD, technical, interface or format sections the change touches; don't load unrelated material for a local change.
- Inspect the working tree, the target diff, relevant callers, configuration and tests, and separate this change from the user's existing modifications.
- Judge the target semantics by the PRD and the current implementation by code and tests; the tests themselves are under review too.
- Don't widen the review to unrelated historical problems unless they directly affect the correctness of this change.

## Review order

1. Product semantics, scope, and whether completion is being faked.
2. Data corruption, compatibility, migration and recovery.
3. Correctness, boundaries, async behaviour and lifecycle.
4. Privacy, security, permissions and logging.
5. Architectural responsibilities, dependency direction and single source of truth.
6. Regression tests, failure paths and verification evidence.
7. Maintainability, complexity and documentation consistency.

Don't report pure style issues that formatters or existing linters catch reliably, unless they expose a real defect. When the project has its own rules or invariants (in project docs or project skills), check them too.

## What to look for

- Unfinished capabilities shown as successful, or mocks leaking into production paths.
- The UI layer touching databases, files, the network, payments or protocol details directly.
- Writes that can partially succeed, overwrite good data, or lose cancellation or retry state.
- Async results that can overwrite newer state after an object is disposed or its input changes.
- Swallowed errors, error classification that depends on fragile strings, logs containing sensitive data.
- Format or schema changes without versioning, migration, rollback and tests against old data.
- Tests that only check implementation details, or that cement wrong product behaviour as expected.
- Documentation and implementation status that don't match actual completeness.

## Severity

- `P0`: may cause data corruption, a security incident, a serious privacy problem, wrong charges or unrecoverable results.
- `P1`: a major functional error, a clear conflict with product semantics, or a likely regression.
- `P2`: an important missed boundary, weak recovery, inverted architecture or a key testing gap.
- `P3`: a non-blocking maintainability improvement with a clear benefit.

Severity describes impact, not personal preference.

## Output

List findings first, ordered by severity. Each has the exact file and line, the trigger condition, the real impact and a workable direction for the fix; add open questions and verification gaps where needed. If nothing is found, say “no blocking issues found” and state the review scope, what was verified and which risks remain uncovered.
