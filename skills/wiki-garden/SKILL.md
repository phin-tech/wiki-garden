---
name: wiki-garden
description: Compile your coding-session experience into persistent knowledge. Use to capture a structured trace of a task that just happened (what worked, what failed) into the Wiki Garden store, and to consolidate accumulated traces into a wiki of reusable patterns. Triggers on "capture a trace", "wiki-garden", "compile my session", "update the wiki", "remember how this went".
metadata:
  homepage: https://github.com/phin-tech/wiki-garden
---

# Wiki Garden

A personal memory system for coding agents. It turns your session experience
into a persistent **wiki** of patterns and (later) evolving **skills**, so the
agent stops relearning the same lessons. Adapted from *WikiSkill* (arXiv
2608.27454).

Runtime lives beside this file: `scripts/` (executables) and
`prompts/`. Refer to them relative to this skill's directory.

## Invocation

- `/wiki-garden <task summary>` — capture a trace of the task that just happened;
  the summary (if given) seeds the **task** field. This is the common case.
- `/wiki-garden` with no argument, or intent like "update the wiki" / "consolidate
  my traces" — run the maintainer instead (see *Consolidate* below).
- The model may also auto-trigger capture when a task clearly just taught
  something worth keeping.

## Store location

All data lives in a store resolved by `scripts/garden-home` (first hit wins):
`$WIKIGARDEN_HOME` → `~/.config/wiki-garden/config` (`home=...`) →
default `~/.config/wiki-garden` (auto-created). Get it with:

```bash
STORE="$(scripts/garden-home)"    # or just `garden-home` if on PATH
```

Layout: `raw/` (traces) · `wiki/patterns/` + `wiki/evolution-log.md` +
`wiki/skill-impact.jsonl` · `skills/` · `eval/`.

## Capture a trace (per task)

When a task just taught you something worth keeping, write a high-signal trace.

1. Resolve the store and `mkdir -p "$STORE/raw"`.
2. Gather objective context you can infer without asking:
   ```bash
   pwd; basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
   git --no-pager diff --stat HEAD 2>/dev/null | tail -20
   git --no-pager log --oneline -5 2>/dev/null
   ```
   From that plus the conversation, draft **task** (seeded by the `/wiki-garden`
   argument if present), **project** (the repo/basename, or `global` if not in
   one), **stack** (langs/frameworks), **tools** used, and **outcome**
   (`success|partial|fail`).
3. Draft **What worked** / **What failed / friction** / **Notes**, then present
   the complete trace and have the user confirm/correct these judgment fields in
   ONE round (not a questionnaire) — your draft is a best guess.
4. Write `"$STORE/raw/$(date +%Y-%m-%dT%H-%M)_<kebab-slug>.md"` (slug = 2–4
   kebab words of the task) in this format:

```markdown
---
task_id: <date-slug>
date: <iso8601>
source: manual
project: <repo-basename or global>
stack: [<...>]
outcome: success | partial | fail
tools: [<...>]
---
## Task
<what was asked>
## What worked
<concrete moves that advanced the task>
## What failed / friction
<dead ends, wrong assumptions, retries>
## Notes
<anything a future session would want to know>
```

Favor specifics (exact commands, paths, the insight that unblocked things).
The friction section is often the most valuable.

## Consolidate traces into the wiki

Run the standalone, model-agnostic maintainer (a PEP 723 `uv` script):

```bash
scripts/garden-maintain              # compile new traces into wiki/patterns
scripts/garden-maintain --dry-run    # preview the patch-plan, change nothing
```

Backend is pluggable via env — nothing is tied to one provider:
- `WIKIGARDEN_LLM=claude` (**default**) — uses the local `claude` CLI (`-p`) and
  your existing Claude Code login; no API key, fully local.
- `WIKIGARDEN_LLM=anthropic` (`ANTHROPIC_API_KEY`) — Messages API directly.
- `WIKIGARDEN_LLM=openai` + `WIKIGARDEN_LLM_BASE_URL` (OpenAI, local vLLM, Ollama).
- `WIKIGARDEN_LLM_MODEL=<id>` for any backend.

The same applies to `scripts/garden-propose` (stages a skill proposal).

The maintainer only ever adds/refines wiki knowledge; it never writes skills and
never wipes existing patterns. Single-trace themes are recorded as
`status: provisional` and promoted once corroborated.

## One iteration: consolidate + propose

To run both steps at once — compile traces into the wiki, then stage at most one
atomic skill proposal:

```bash
scripts/garden-evolve            # maintain, then propose
scripts/garden-evolve --dry-run  # preview both, write nothing
```

`garden-propose` reads the wiki + existing skills + the `skill-impact.jsonl`
ledger and stages a proposal under `<store>/proposals/<ts>_<name>/` (SKILL.md +
PURPOSE.md + proposal.json). It **never activates** a skill — review the staged
proposal before promoting it into `skills/`. Proposals are conservative:
single-trace patterns are usually too weak, so `no_change` is common and fine.

## Optional: put scripts on PATH

```bash
ln -sf "$PWD/scripts/garden-home"     ~/.local/bin/garden-home
ln -sf "$PWD/scripts/garden-maintain" ~/.local/bin/garden-maintain
```

## Notes for agents

- Never fabricate trace content — the friction/notes fields must reflect what
  actually happened this session; ask the user rather than guess.
- The trace store can contain details from real work; treat it as private.
