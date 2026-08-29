---
description: Run one Wiki Garden evolution iteration — consolidate traces into the wiki, then propose one atomic skill (staged for gating, not activated).
argument-hint: [--dry-run]
allowed-tools: Bash
---

Run one Wiki Garden evolution iteration by invoking the sequencer, forwarding any
argument (e.g. `--dry-run`):

```bash
garden evolve $ARGUMENTS
```

This does two things, in order:
1. **maintain** — compile unprocessed `raw/` traces into `wiki/patterns/`.
2. **propose** — from the updated wiki, stage at most one atomic skill under
   `<store>/proposals/` (it is NOT activated; gating happens separately).

After it runs, summarize for the user: what the maintainer changed (patterns
created/refined) and whether a skill was proposed (and where it was staged, or
why `no_change`). If a proposal was staged, offer to review its `SKILL.md` diff.
Do not activate or move any proposal into `skills/` — that is the gate's job.
