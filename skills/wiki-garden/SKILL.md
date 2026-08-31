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

Runtime lives beside this file as the `wiki_garden` Python package (the CLI, its
`_*.py` modules, the model-agnostic `prompts/`, and the compiled `web-dist/`),
plus a `scripts/garden` launcher. **Resolve the CLI in this order:**

1. If `garden` is on PATH — the user ran `uv tool install` (see *Install* below) —
   just call `garden <subcommand>`.
2. Otherwise run the bundled launcher directly. It's a `uv` script: executing it
   pulls `typer` on its own, so no install or PATH setup is needed:

   ```bash
   <skill-dir>/scripts/garden home      # <skill-dir> = the directory holding this SKILL.md
   ```

Throughout this doc `garden <cmd>` means *the resolved CLI* — substitute
`<skill-dir>/scripts/garden <cmd>` whenever it isn't on PATH.

## Invocation

- `/wiki-garden <task summary>` — capture a trace of the task that just happened;
  the summary (if given) seeds the **task** field. This is the common case.
- `/wiki-garden` with no argument, or intent like "update the wiki" / "consolidate
  my traces" — run the maintainer instead (see *Consolidate* below).
- The model may also auto-trigger capture when a task clearly just taught
  something worth keeping.

## Store location

All data lives in a store resolved by `garden home` (first hit wins):
`$WIKIGARDEN_HOME` → `~/.config/wiki-garden/config` (`home=...`) →
default `~/.config/wiki-garden` (auto-created). Get it with:

```bash
STORE="$(garden home)"    # or <skill-dir>/scripts/garden home if not on PATH
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
garden maintain              # compile new traces into wiki/patterns
garden maintain --dry-run    # preview the patch-plan, change nothing
```

Backend is pluggable via env — nothing is tied to one provider:
- `WIKIGARDEN_LLM=claude` (**default**) — uses the local `claude` CLI (`-p`) and
  your existing Claude Code login; no API key, fully local.
- `WIKIGARDEN_LLM=anthropic` (`ANTHROPIC_API_KEY`) — Messages API directly.
- `WIKIGARDEN_LLM=openai` + `WIKIGARDEN_LLM_BASE_URL` (OpenAI, local vLLM, Ollama).
- `WIKIGARDEN_LLM_MODEL=<id>` for any backend.

The same applies to `garden propose` (stages a skill proposal).

The maintainer only ever adds/refines wiki knowledge; it never writes skills and
never wipes existing patterns. Single-trace themes are recorded as
`status: provisional` and promoted once corroborated.

## One iteration: consolidate + propose

To run both steps at once — compile traces into the wiki, then stage at most one
atomic skill proposal:

```bash
garden evolve            # maintain, then propose
garden evolve --dry-run  # preview both, write nothing
```

`garden propose` reads the wiki + existing skills + the `skill-impact.jsonl`
ledger and stages a proposal under `<store>/proposals/<ts>_<name>/` (SKILL.md +
PURPOSE.md + proposal.json). It **never activates** a skill — review the staged
proposal before promoting it into `skills/`. Proposals are conservative:
single-trace patterns are usually too weak, so `no_change` is common and fine.

## Install targets: which agents get accepted skills

When you accept a skill at the gate (globally), it's installed for the agents in
`install_targets` (config, set at `garden init` — comma list, or `none`):

- `claude-code` (**default**) — a native `~/.claude/skills/<name>` symlink, no
  dependencies.
- `codex`, `cursor`, `opencode`, and others (incl. `pi` via the shared
  `.agents/skills` convention) — installed through the [`npx skills`](https://github.com/vercel-labs/skills)
  CLI, which knows each agent's directory. Requires `npx`; if it's missing the
  accept still succeeds and prints a manual `npx skills add …` hint.

`SKILL.md` is identical across agents, so only the install location differs.
`install_method=symlink|copy` controls linking vs copying.

## Install

You don't have to install anything to use the CLI — the bundled
`scripts/garden` launcher runs via `uv` with zero setup (resolution step 2
above). To get a first-class `garden` command on PATH instead:

```bash
# From anywhere — installs `garden` as an isolated uv tool (no clone needed):
uv tool install "git+https://github.com/phin-tech/wiki-garden.git#subdirectory=skills/wiki-garden"

# Or, from a checkout of this repo, the dev installer (symlinks so `git pull` updates it):
./install.sh
```

Both leave `garden` on PATH, after which resolution step 1 applies. A plain
`ln -sf "$PWD/scripts/garden" ~/.local/bin/garden` from this directory also works.

## Notes for agents

- Never fabricate trace content — the friction/notes fields must reflect what
  actually happened this session; ask the user rather than guess.
- The trace store can contain details from real work; treat it as private.
