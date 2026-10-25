
## Verification and reporting

- Use the toolchain and commands the project specifies (see the project's `AGENTS.md` or `docs/AI_RULES.md`).
- Run the checks closest to the change first, then widen according to risk; don't run builds that compete for resources in parallel.
- Check pages and screens with scripted checks that report in text (console errors, horizontal scrolling, truncated text, elements outside the viewport, small tap targets, controls without an accessible name) rather than by reading screenshots. Look at screenshots only for an occasional visual check at the end of a stage.
- A bug fix normally adds a regression test that fails on the old implementation; if that isn't practical, explain why and how to verify by hand.
- Never change product rules to make tests pass, and never delete or weaken failing tests.
- Report a check as “passed” only if it actually ran and succeeded; list skipped, blocked and failed checks honestly.
