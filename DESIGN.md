# Wiki Garden — Personal Coding-Agent Adaptation

An implementation of *WikiSkill: Compiling Agent Experience into Persistent
Knowledge for Skill Evolution* (arXiv 2608.27454), adapted from a benchmark
reproduction into a working system for daily software engineering across many
stacks.

The paper's insight: naive "let the agent write itself skills" loses the
*reasoning* behind each skill, so the agent can't build on accumulated
knowledge. Wiki Garden fixes this by separating three layers — immutable traces,
a persistent wiki of patterns, and active skills — and adding discipline:
atomic proposals, traceability from each skill back to the pattern that
motivated it, and gated acceptance with a memory of past decisions.

Here, the **Inference Agent is Claude Code in normal daily use**. This project
is the *compiler* that turns session history into durable skills + wiki.

## Design decisions

| Decision | Choice |
|---|---|
| Gating | Human-in-the-loop diff **and** retro-eval against past real tasks |
| Trigger | Manual `/garden-evolve` **and** weekly scheduled run |
| Code home | This repo, packaged as a skills.sh-installable skill (`skills/wiki-garden`) |
| Data home | `~/.config/wiki-garden` by default (machine-local; git-init to version) |
| LLM backend | Pluggable; default `claude` CLI (no key), or `anthropic`\|`openai`-compatible |

## Code vs data (Phase 0)

Two locations, cleanly separated:

**Code** — this repo, version-controlled, synced across machines. The runtime is
packaged as a self-contained skill so Wiki Garden itself is installable via
skills.sh (`npx skills add phin-tech/wiki-garden`):
```
wiki-garden/
  skills/
    wiki-garden/               # the shippable skill (skills.sh discovers SKILL.md)
      SKILL.md               # self-sufficient workflow: capture + consolidate
      scripts/
        garden-home       # resolves the store root portably (env/config/default)
        garden-maintain   # standalone maintainer (PEP 723 / uv, pluggable LLM)
        garden-propose    # standalone skill proposer (stages to proposals/)
        garden-evolve     # sequencer: maintain then propose (forwards flags)
        garden-gate       # gate: retro-eval + accept/reject + promote + ledger
        _garden.py              # shared backend + store helpers (imported, not on PATH)
      prompts/
        wiki-maintainer.md   # model-agnostic maintainer prompt
        skill-proposer.md    # model-agnostic proposer prompt
        retro-eval.md        # model-agnostic retro-eval judge prompt
  agents/                    # Claude Code subagents (wiki-maintainer, skill-proposer)
  commands/                  # /garden-evolve (author convenience; capture lives in the skill)
  install.sh                 # dev install: symlinks scripts→PATH, commands, agents, skill
  DESIGN.md
```

Two install paths: `npx skills add phin-tech/wiki-garden` gives anyone the skill
(a snapshot copy with its bundled scripts); `./install.sh` is the author dev
install (symlinks so `git pull` propagates, plus the slash command + subagent
that skills.sh does not carry).

**Data (the store)** — default `~/.config/wiki-garden/`, auto-created, machine-local
(git-init it yourself if you want the data versioned):
```
<store>/                     # resolved by garden-home (skills/wiki-garden/scripts/)
  raw/                       # immutable execution traces (append-only)
    2026-08-29T14-03_<slug>.md
  wiki/                      # persistent knowledge base (patched, never wiped)
    patterns/                # one file per failure-mode/strategy pattern
      <pattern-slug>.md
    evolution-log.md         # human narrative of every iteration (markdown)
    skill-impact.jsonl       # every accept/reject decision (JSONL, machine-queried)
    .processed.log           # cursor: trace filenames the maintainer consumed
  skills/                    # active (gated-in) procedural knowledge
    <skill-name>/
      SKILL.md               # the skill itself (Claude Code skill format)
      PURPOSE.md             # traceability: which wiki pattern(s) motivated it
  proposals/                 # staged, ungated skill proposals awaiting the gate
    <ts>_<skill-name>/       # SKILL.md + PURPOSE.md + proposal.json
  tools/                     # active (gated-in) executables — the tools layer
    <name>/                  # <prefix><name> executable + TOOL.md + PURPOSE.md
  tool-proposals/            # staged, ungated tool proposals awaiting the gate
    <ts>_<name>/             # <prefix><name> + TOOL.md + PURPOSE.md + proposal.json
  eval/
    stash/                   # curated past real tasks for retro-eval
    results/                 # retro-eval outputs per proposal
```

### File formats

**raw/ trace** — written per task by the capture hook:
```markdown
---
task_id: <uuid>
date: <iso8601>
source: manual | hook             # /wiki-garden capture vs session-end hook
stack: [python, pytest]           # detected/declared
outcome: success | partial | fail
tools: [Edit, Bash, Grep]
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

**wiki/patterns/<slug>.md**:
```markdown
---
pattern_id: <slug>
status: active | superseded
stacks: [python, react]           # or [*] for cross-stack
first_seen: <date>
trace_refs: [<task_id>, ...]      # provenance
---
## Pattern
<the recurring failure mode or winning strategy>
## Evidence
<links to raw/ traces that established it>
## Guidance
<what to do about it — may or may not become a skill>
```

**skills/<name>/PURPOSE.md** — the traceability link the paper requires:
```markdown
pattern: <pattern_id>
proposed: <date>
gate: human=accepted retro=passed
rationale: <one line: why this skill exists>
```

**wiki/skill-impact.jsonl** — append-only, one JSON record per decision;
machine-queried by the Skill Proposer to avoid re-proposing rejected ideas:
```json
{"date":"2026-08-29","proposal":"add-skill:foo","pattern":"bar","human":"accepted","retro":"passed","decision":"accepted","note":"..."}
```
Format rationale: narrative logs (`evolution-log.md`) stay markdown for human
review during gating; the machine-parsed decision ledger is JSONL; the
`.processed.log` cursor is plain newline-delimited filenames (diffed with `comm`).

## Cross-repo / cross-machine invariant

This system is used *from within other projects* (daily eng across stacks) and
across machines (home, work), so the store root is **resolved at runtime**, not
hardcoded. `garden-home` returns the absolute store path using the first
hit of:

1. `$WIKIGARDEN_HOME` environment variable
2. `~/.config/wiki-garden/config` — a line `home=/abs/path/to/store`
   (machine-local, never committed)
3. default: `~/.config/wiki-garden` — auto-created with the store skeleton on
   first call; identical path on every machine, so zero-config out of the box

Every command, hook, and agent calls `garden-home` instead of embedding
a path.

- Source of truth for commands/agents lives in this repo (`commands/`, `agents/`).
- Installed copies go to `~/.claude/commands/` and `~/.claude/agents/` so they
  resolve from any cwd. Skills export to `~/.claude/skills/`.
- Traces always write to `<resolved-home>/raw/`, never `./raw/`.

## Trace capture: two paths into `raw/`

Both write the same trace format above; they differ in when and how.

- **`/wiki-garden <task summary>`** (manual, per-task): the `wiki-garden` skill's
  capture flow — invoked when something worth remembering just happened. It reads
  the current session context and prompts for the parts it can't infer, producing
  a deliberate high-signal trace. This is the primary, highest-quality fuel for
  the loop, and the single source of truth for the trace format.

  Flow: infer `task`, `stack`, `tools`, and `outcome` from the session →
  ask the user to confirm/correct and to fill **What worked** /
  **What failed** / **Notes** (pre-filled with the model's best guess, user
  edits inline) → write `raw/<timestamp>_<slug>.md`.

- **Session-end hook** (automatic, per-session, Phase 1): coarse safety net so
  nothing is lost when you forget to capture. Lower signal; flagged
  `source: hook` in frontmatter so the Wiki Maintainer can weight manual traces
  higher.

## Agent roles

- **Wiki Maintainer** (`agents/wiki-maintainer` + `garden-maintain`):
  reads recent `raw/` traces + current wiki, emits **patch ops**
  (create/append/replace) to `wiki/`. Runs on every iteration and its output
  persists *regardless* of any skill decision — the wiki is the long-term memory
  even when no skill changes. Runnable via Claude Code subagent OR the
  standalone, model-agnostic runner (see Execution model).
- **Skill Proposer** (`agents/skill-proposer` + `garden-propose`): reads wiki
  patterns + existing skills + the ledger, proposes **exactly one atomic** skill
  change (new skill or edit) — or `no_change`. Stages it under
  `proposals/<ts>_<name>/` (SKILL.md + PURPOSE.md + proposal.json); it **never
  activates** skills — gating does. Reads `skill-impact.jsonl` first to avoid
  resurrecting rejected ideas. Same dual-mode + JSON-plan + pluggable backend as
  the maintainer.
- **Gate** (Phase 4): (1) retro-eval — replay the staged proposal against
  `eval/stash/` tasks, reject on regression; (2) human diff — you approve/reject.
  Both outcomes recorded in `skill-impact.jsonl`; accepted proposals move from
  `proposals/` into `skills/`.

## Execution model — Claude-independent

The agent *roles* are prompts, not hard dependencies on Claude Code. Each role
runs two ways over the **same model-agnostic prompt**:

- **Interactive (Claude Code)**: the subagent under `agents/` — convenient
  inside a session, uses Claude Code's tools directly.
- **Standalone (any LLM)**: deterministic runners (`garden-maintain`,
  `garden-propose`) that do NOT need a tool-using agent. The LLM is asked for
  a **JSON plan**; plain code validates and applies/stages it. Shared backend +
  store helpers live in `scripts/_garden.py`.

### Patch-plan contract

The maintainer LLM returns one JSON object; the runner applies it deterministically:
```json
{
  "ops": [
    {"op":"create_pattern","id":"<slug>","content":"<full markdown>"},
    {"op":"append_evidence","id":"<slug>","trace_ref":"<id>","bullet":"<text>"},
    {"op":"replace_section","id":"<slug>","section":"Guidance","content":"<text>"},
    {"op":"log","entry":"<markdown block>"}
  ],
  "processed": ["<trace-file.md>", ...],
  "report": "<human summary>"
}
```
This keeps the model's job to *reasoning + JSON* (portable across Qwen, GPT,
local models) and keeps filesystem mutation in audited, deterministic code.

### Pluggable backend

LLM access goes through one thin adapter selected by env:
- `WIKIGARDEN_LLM=claude` (**default**) — shells out to the local `claude` CLI
  (`claude -p --system-prompt …`), using the existing Claude Code login. No API
  key, fully local, zero setup — the recommended way to run locally.
- `WIKIGARDEN_LLM=anthropic` — Messages API (`ANTHROPIC_API_KEY`)
- `WIKIGARDEN_LLM=openai` — OpenAI-compatible `/chat/completions`; set
  `WIKIGARDEN_LLM_BASE_URL` to point at OpenAI, a local vLLM, or Ollama
- `WIKIGARDEN_LLM_MODEL` — model id for the chosen backend

Because the default backend is the `claude` CLI, "Claude-independent" means the
*architecture* isn't bound to it (swap one env var for a local model), not that
Claude is avoided — the default deliberately uses the login you already have.

Runner is a **PEP 723 / `uv run` script** (`garden-maintain`) — inline
script metadata, launched via `#!/usr/bin/env -S uv run --script`, stdlib-only
(urllib + json, zero declared deps) so `uv` pins the interpreter with nothing to
install. Flags: `--dry-run` (print plan, mutate nothing) and `--plan-file`
(apply a given JSON plan, skipping the LLM) — the latter makes the deterministic
applier testable without any API key.

## Skills Layer — skills.sh compatible

Two things are skills.sh-installable: **Wiki Garden itself** (the `skills/wiki-garden`
skill above) and the **skills Wiki Garden evolves** (Skills Layer output). Both use
the `skills` CLI (`npx skills add <owner/repo>`, github.com/vercel-labs/skills):

- A skill is a directory `skills/<name>/SKILL.md` with YAML frontmatter
  (`name`, `description`) — exactly our format, so skills are installable as-is.
- `PURPOSE.md` sits alongside `SKILL.md`; the installer ignores non-`SKILL.md`
  files, so our traceability metadata rides along without breaking installs.
- To publish for `skills add`, the store's `skills/` must live in a git repo
  with that layout (the optional "git-init your store" path) — or be mirrored to
  a dedicated published skills repo.
- Set `metadata.internal: true` in frontmatter to keep a skill out of the
  public skills.sh directory while still installable.

## Tools layer

A second active layer beside skills: where a **skill** is advisory markdown, a
**tool** is a reusable **executable** promoted from an ephemeral script. Same
compiler (`raw → wiki → {skills, tools}`), same propose→stage→gate pipeline;
different artifact.

- **Capture** (`garden-tool` + `/garden-tool`): take a raw one-off script → an
  LLM **generalizer** lifts hardcoded values into flags, **strips secrets**
  (env/credential-chain instead), adds `--help`, targets the configured runtime,
  and defaults destructive scripts to a preview posture. Staged under
  `tool-proposals/` — never installed until gated.
- **Config** (machine-local, in `~/.config/wiki-garden/config`):
  ```
  tool_prefix  = gt-     # namespaces every tool (tab-completable); user-set
  tool_runtime = bash    # default runtime: bash | uv | node; per-tool override
  tool_guidance = ...    # short inline house-style note appended to the generalizer
  ```
- **House-style prompt overlays** (`~/.config/wiki-garden/prompts/`): the
  generalizer appends `tool.md` (always) and `tool.<runtime>.md` (for the chosen
  runtime) so the user injects their own conventions — e.g. "uv scripts with
  PEP 723 and pinned deps, click for args" vs "bash with set -euo pipefail and
  getopts". Style/runtime only; the safety rules (strip secrets, preview
  destructive ops) always override. The overlay mechanism (`prompt_overlays`) is
  generic and can later augment the maintainer/proposer/retro prompts too.
- **Gate** (`garden-tool-gate` + `/garden-tool-gate`): mandatory **human code
  review** (`show` prints the full source) plus a **static** safety review — an
  LLM judge that reads the code (secrets / unguarded destructive ops / injection
  / correctness) and never executes it; advisory, the human decides. Accept →
  move to `tools/`, symlink `<prefix><name>` onto `~/.local/bin` (PATH), record in
  `wiki/tool-impact.jsonl`; reject archives + records. The review is resilient: a
  backend failure yields `skipped`, never blocking a human-authorized accept.
- **Discovery** (T3, planned): a generated **Runme-compatible catalog**, surfaced
  as a `wiki-garden-tools` skill, so the agent reaches for a tool instead of
  rewriting it. Executable = canonical artifact; catalog = index + docs.
- **Auto-mine** (T4, planned): mine traces for recurring scripts and propose
  promoting them (the ambient path; manual capture is T1).

Tool build phases: **T1 ✅** capture + generalize + stage. **T2 ✅** gate
(`garden-tool-gate`: human code review + static safety review + promote/install +
`tool-impact.jsonl`; accept/reject/install validated deterministically, live
review flagged a planted secret + unguarded `aws s3 rm`). **T3** catalog skill
(Runme). **T4** auto-mine.

## Evolution iteration (one run of `/garden-evolve`)

1. Collect `raw/` traces since last iteration.
2. Wiki Maintainer patches `wiki/` → commit (wiki always advances).
3. Skill Proposer emits one atomic proposal (or "no change warranted").
4. Retro-eval the proposal against `eval/stash/`.
5. Present human diff with retro-eval result attached.
6. Record decision in `skill-impact.md`; if accepted, write skill + PURPOSE.md,
   export to `~/.claude/skills`, append to `evolution-log.md`.

## Build phases

- **Phase 0** — ✅ store contract, portable resolver (`garden-home`),
  installer, README.
- **Phase 1** — trace capture. ✅ `/wiki-garden` skill capture flow (manual,
  per-task). ◻ session-end hook (automatic, per-session) → `raw/`.
- **Phase 2** — Wiki Maintainer. ✅ Claude Code subagent (prompt validated on a
  real trace → 3 patterns). ✅ standalone `garden-maintain` (PEP 723/uv,
  JSON patch-plan, pluggable anthropic|openai backend); applier validated across
  all op types via `--plan-file`. ◻ live LLM smoke-test (needs an API key/local
  model).
- **Phase 3** — Skill Proposer. ✅ Claude Code subagent + standalone
  `garden-propose` (PEP 723/uv, shared `_garden.py`); stages atomic, traceable
  proposals to `proposals/` without activating; stager validated via `--plan-file`.
  ✅ live LLM smoke-test via `claude` backend (no key).
- **Phase 4** — gating. ✅ `garden-gate` (retro-eval LLM judge over
  `eval/stash/`, advisory + skip-when-empty; human accept/reject; `skill-impact.jsonl`
  writes on both; promote `proposals/`→`skills/`; install to `~/.claude/skills`) +
  `/garden-gate` command. Accept/reject/retro all validated (retro live).
- **Phase 5** — orchestration. ✅ `garden-evolve` sequencer (maintain→propose)
  + `/garden-evolve` command. ◻ insert the gate between propose and activate;
  ◻ weekly schedule.

## Open questions

- Trace granularity is now resolved: `/wiki-garden` capture handles per-task
  (deliberate, high-signal) and the hook handles per-session (safety net).
  Remaining question: should the hook be opt-in per session to avoid noise?
- `eval/stash/` seeding: retro-eval is only as good as the stash. Start by
  hand-curating ~10 representative past tasks across your main stacks.
