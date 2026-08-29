# Wiki Garden

A personal coding-agent memory system: it compiles your Claude Code session
experience into a persistent **wiki** of patterns and a set of evolving
**skills**, so the agent gets better across sessions and stacks instead of
relearning the same lessons every time.

Adapted from *WikiSkill: Compiling Agent Experience into Persistent Knowledge
for Skill Evolution* (arXiv 2608.27454). See [DESIGN.md](DESIGN.md) for the full
architecture and how it maps to the paper.

## Layout

- **This repo** = code (commands, agents, `bin/`). Version-controlled, synced
  across machines.
- **`~/.config/wiki-garden/`** = your data (`raw/ wiki/ skills/ eval/`).
  Auto-created on first use, machine-local by default.

## Install

**As a skill (anyone):** Wiki Garden is packaged as a self-contained skill, so it
installs via the skills.sh CLI — this copies the skill (with its bundled
scripts) into `~/.claude/skills/wiki-garden/`:

```sh
npx skills add phin-tech/wiki-garden
```

**Dev install (this repo's author):** run the installer once per machine. It
symlinks the scripts onto your PATH and the slash command + subagent into
`~/.claude/`, then auto-creates the store:

```sh
./install.sh
```

Because it uses symlinks, a later `git pull` here updates the installed copies
automatically (re-run `./install.sh` only after *adding* a new script, command,
or agent). If `~/.local/bin` isn't on your PATH, add it so the scripts resolve
in shells.

To see the resolved store path at any time:

```sh
garden-home
```

### Store location (optional)

The store root is resolved by `garden-home` in this order:

1. `$WIKIGARDEN_HOME` environment variable
2. `~/.config/wiki-garden/config` with a line `home=/abs/path/to/store`
3. default: `~/.config/wiki-garden`

Set the env var or config only if you want the store somewhere else.

### Versioning your knowledge (optional)

By default the store is **local to each machine** — your wiki and skills on your
work laptop are independent from your home machine. If you'd rather carry the
accumulated knowledge across machines (and keep a history of how it evolved),
turn the store into its own git repo:

```sh
cd "$(garden-home)"
git init
git add -A && git commit -m "wiki-garden store"
git remote add origin <your-private-remote>
git push -u origin main
```

Keep this separate from the code repo — it's your personal knowledge, and it can
contain details from real work tasks, so a **private** remote is strongly
recommended.

## Commands

- `/wiki-garden <task summary>` — capture a structured trace of what just happened
  into `raw/` (the `wiki-garden` skill). Run it whenever a task taught you
  something worth keeping. With no argument it can also run consolidation.
- `garden-maintain` — compile unprocessed traces into `wiki/` patterns.
  Standalone `uv` script (PEP 723), model-agnostic: set `WIKIGARDEN_LLM`
  (`anthropic`|`openai`, the latter covers local vLLM/Ollama via
  `WIKIGARDEN_LLM_BASE_URL`). `--dry-run` previews the patch-plan; `--plan-file`
  applies a given plan without calling any LLM. Also available inside Claude Code
  as the `wiki-maintainer` subagent.
- `garden-propose` — propose one atomic, reusable skill grounded in a wiki
  pattern, staged to `proposals/` for gating (never auto-activated). Same
  `uv`/model-agnostic shape as `garden-maintain` (`--dry-run`, `--plan-file`).
  Also available as the `skill-proposer` subagent.
- `garden-evolve` (`/garden-evolve`) — one iteration: runs `maintain` then
  `propose` in sequence, forwarding flags (`--dry-run`, `--backend`, `--model`).
- `garden-gate` (`/garden-gate`) — review staged proposals and accept or
  reject: `list` / `show <name>` / `retro <name>` / `accept <name>` /
  `reject <name> --note`. Retro-eval is advisory (skips when `eval/stash/` is
  empty); accept promotes `proposals/`→`skills/`, installs to `~/.claude/skills`,
  and records the decision in `skill-impact.jsonl`.

## Status

Early build. Implemented: store resolution + scaffolding. In progress: trace
capture. See [DESIGN.md](DESIGN.md) build phases for the roadmap.
