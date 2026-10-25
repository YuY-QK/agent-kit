---
name: flutter-development
description: Implement, fix or refactor Flutter/Dart code following layering, Riverpod, local-first, localisation and FVM verification rules. Use it for coding tasks in Flutter projects; don't use it for pure product or UI-proposal discussions.
---

# Flutter development

Deliver Flutter/Dart changes that are small in scope, complete in behaviour, testable and within the project's boundaries.

## Before you start

- Read the project rules, PRD, technical or format sections that affect this change; don't load unrelated material for a local implementation.
- Check `git status` and the relevant call chain, and protect the user's existing changes; find how neighbouring code, shared components, providers, repositories and tests are already written.
- Define current behaviour, target behaviour, non-goals and done-criteria; raise product or architecture conflicts first.
- When the project root has a `.fvmrc`, prefix every command with `fvm` (`fvm flutter ...`, `fvm dart ...`) to use the project's Flutter version.

## Structure

- If the global rules name the user's own scaffold, generate new projects with it and follow its structure.
- Prefer feature-first: `lib/app` (app root, routing, configuration), `lib/core` (theme, error types, stable shared capabilities), `lib/features/<feature>`; keep `main.dart` thin.
- Dependency direction: screens/widgets → controller or use case → repository → data source or platform adapter. Small features don't need empty interfaces or layers.
- Before sharing code across features, confirm it is a stable shared concept; otherwise keep it in its feature.
- Declare routes centrally and pass parameters as explicit types or stable serialised forms; don't build route paths by string concatenation.

## Implementation principles

- Make the smallest complete change; don't refactor neighbouring modules along the way.
- Widgets only render, hold local interaction state and forward events; they don't touch databases, files, the network or payment SDKs, or parse protocols.
- Riverpod providers compose dependencies and don't hold global mutable state with an uncontrolled lifecycle; async state handles repeated calls, stale results, cancellation and disposal.
- Model complex state with sealed classes, enums or state objects rather than piles of mutually exclusive booleans and magic strings.
- Make randomness, clocks, audio, persistence and platform capabilities replaceable dependencies so they can be tested.
- Side effects such as saving, exporting and downloading define success, failure, cancellation, retry and cleanup; never fake purchase, share or remote success.
- User-visible text goes into ARB files and localisation output is regenerated through the generation step; don't edit generated files by hand.
- Add only the dependencies needed now; before adding or upgrading a package, explain why, the platform impact and the lockfile change.
- When native code changes, also check the matching platform implementation and Gradle/Xcode configuration.

## Bugs and refactoring

- Reproduce a bug and locate the root cause first; normally add a regression test that fails on the old implementation.
- Refactoring keeps observable behaviour; separate structural changes from behaviour changes where possible.
- Before deleting code, check routes, provider overrides, serialisation, native entry points and test callers.

## Verification

Step up by risk (prefix with `fvm` when there is a `.fvmrc`):

1. `dart format <changed files>`
2. The directly relevant `flutter test <test path>`
3. `flutter analyze`
4. For broad, data-related or release-related changes: the full `flutter test` and the necessary platform builds

Don't run several Flutter/Gradle builds in parallel. Database, file-format, repository, secure-storage and native-plugin changes need additional failure and compatibility tests.

## Delivery

Describe the behaviour change and key design, the verification actually run, checks not run or blocked, compatibility, platform impact and remaining risks. Never describe plans, placeholders or mocks as finished capabilities.
