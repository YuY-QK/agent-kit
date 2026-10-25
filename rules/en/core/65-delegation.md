
## Subagents and usage

- When work is split across subagents (parallel tasks, batches, delegated implementation), follow the `orchestrate` skill: it covers model choice, how many to run, merging and reporting.
- Running several subagents at once doesn't reduce total usage; it only finishes sooner. Usage is saved by keeping each task small, keeping the main conversation short and matching the model to the difficulty.
