
## Handoff before running out

- Before the usage limit or the context runs out, write a handoff note so the next session can pick up exactly where this one stopped without rereading the long conversation: `docs/HANDOFF.md` in the project (in the current working folder if there is no project).
- Contents, briefly: the task and its goal; what is done and verified; where it stopped (the step in progress, files changed but not committed, commands that were running); the next concrete steps; decisions made and open questions; what to read first. Write facts and paths, not the conversation's history.
- I usually can't see exactly how much usage is left, so don't wait for the last moment: write or update the note at the end of each stage of a long task, and right away when there are signs the limit is near (usage or context warnings, the conversation being compacted). Keep it current rather than complete.
- In a cloud session the container doesn't survive, so commit and push the note on the working branch.
- At the start of a session, if `docs/HANDOFF.md` exists, read it before anything else, together with `docs/progress.md`. Once you understand where the work stopped, move anything that should last (status, plan, open items) into `docs/progress.md`, then delete the note (and commit the deletion if it was committed), and continue.
