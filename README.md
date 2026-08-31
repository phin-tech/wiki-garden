# Wiki Garden

This tool is an implementation of [*WikiSkill: Compiling Agent Experience into Persistent Knowledge
for Skill Evolution*](https://arxiv.org/abs/2608.27454) (arXiv 2608.27454). It's been expanded to try and have it build tools aka re-usable scripts. I've found many times reaching for scripts that I had used in previous sessions to manage things like AWS queries, DB inspection, Observability etc. This is hopefully something that can help do that both when the user initiates it as well as automatically..

Adapted from the paper linked above. See [DESIGN.md](DESIGN.md) for the full
architecture and how it maps to the paper.

**Most of what is below is LLM generated. My apologies in advance**

## Layout

- **This repo**: the code — the `garden` CLI (a Typer app in the `wiki_garden`
  package under `skills/wiki-garden/`, installable with `uv` or runnable via its
  bundled launcher), the `/wiki-garden` and `/garden-*` commands, the subagents,
  the skill, and the `web/` UI. Version-controlled.
- **Your store** (`~/.config/wiki-garden/` by default): everything the garden
  accumulates for you. `garden` creates the skeleton on first run:
  - `raw/` — captured traces (one task each)
  - `wiki/patterns/` — consolidated patterns; `wiki/evolution-log.md`,
    `wiki/skill-impact.jsonl`, `wiki/.processed.log`
  - `proposals/` / `tool-proposals/` — staged, awaiting the gate
  - `skills/` / `tools/` — accepted, promoted outputs
  - `eval/stash/` + `eval/results/` — retro-eval material

The **brain is global** (one store per machine holds all your traces and wiki),
but **outputs can be scoped**: an accepted skill or tool installs either globally
(for you, everywhere) or into a specific project's `.claude/` (committable, shared
with that repo) — see `--scope` under [Commands](#commands).


## Install

**As a skill (anyone):** Wiki Garden is packaged as a self-contained skill, so it
installs via the skills.sh CLI — this copies the skill (with its bundled
`wiki_garden` package) into `~/.claude/skills/wiki-garden/`:

```sh
npx skills add phin-tech/wiki-garden
```

The `garden` CLI ships inside that skill and needs no separate install: the
bundled `scripts/garden` launcher runs via `uv` (it pulls its own `typer`), so an
agent can call `~/.claude/skills/wiki-garden/scripts/garden <cmd>` with zero
setup. The skill automatically prefers a `garden` on PATH when one exists.

**As a `uv` tool (a real `garden` command, no clone):** for a first-class
`garden` on your PATH, install the package straight from the repo subdirectory:

```sh
uv tool install "git+https://github.com/phin-tech/wiki-garden.git#subdirectory=skills/wiki-garden"
garden home
```

Upgrade later with `uv tool upgrade wiki-garden`. (This gives you the CLI; run
`npx skills add phin-tech/wiki-garden` too if you also want the `/wiki-garden`
skill wired into your agents.)

**Dev install (contributor):** run the installer once per machine. It
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
garden home
```

### Store location (optional)

The store root is resolved by `garden home` in this order:

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
cd "$(garden home)"
git init
git add -A && git commit -m "wiki-garden store"
git remote add origin <your-private-remote>
git push -u origin main
```

Keep this separate from the code repo — it's your personal knowledge, and it can
contain details from real work tasks, so a **private** remote is strongly
recommended.

## Commands

- `garden tend` — open a local web UI to browse and **tend** the garden: review
  staged skill proposals and tools and accept/reject them from the browser, and
  read patterns, traces, and the evolution log. Serves a compiled Svelte app
  (built from `web/`, shipped in `skills/wiki-garden/wiki_garden/web-dist/`) over a
  stdlib HTTP server — no JS toolchain needed at runtime. `--port` / `--host`
  to change the bind, `--no-open` to skip auto-opening the browser. See
  [`web/README.md`](web/README.md) for the build process.

  ![The `garden tend` web UI](docs/img/garden-tend-web.png)
- `/wiki-garden <task summary>` — capture a structured trace of what just happened
  into `raw/` (the `wiki-garden` skill). Run it whenever a task taught you
  something worth keeping. With no argument it can also run consolidation.
- `garden maintain` — compile unprocessed traces into `wiki/` patterns.
  The LLM backend is pluggable via `--backend` / `$WIKIGARDEN_LLM`: the default
  `claude` drives your local Claude Code login (**no API key**), or use
  `anthropic` / `openai` (the latter covers local vLLM/Ollama via
  `WIKIGARDEN_LLM_BASE_URL`). `--dry-run` previews the patch-plan; `--plan-file`
  applies a given plan without calling any LLM. Also available inside Claude Code
  as the `wiki-maintainer` subagent.
- `garden propose` — propose one atomic, reusable skill grounded in a wiki
  pattern, staged to `proposals/` for gating (never auto-activated). Same
  backend/flags as `garden maintain` (`--backend`, `--model`, `--dry-run`,
  `--plan-file`). Also available as the `skill-proposer` subagent.
- `garden evolve` (`/garden-evolve`) — one iteration: runs `maintain` then
  `propose` in sequence, forwarding flags (`--dry-run`, `--backend`, `--model`).
- `garden gate` (`/garden-gate`) — review staged proposals and accept or
  reject: `list` / `show <name>` / `retro <name>` / `accept <name>` /
  `reject <name> --note`. Retro-eval is advisory (skips when `eval/stash/` is
  empty) and records the decision in `wiki/skill-impact.jsonl`. `accept` promotes
  `proposals/`→ the store's `skills/`; by default (`--scope global`) it also
  symlinks the skill into `~/.claude/skills` (`--no-install` skips that), while
  `--scope project [--project-dir <repo>]` writes it into that repo's
  `.claude/skills/` instead so it can be committed and shared.

### Tools layer

Beside skills, Wiki Garden can promote an ephemeral script into a reusable CLI
**tool**:

- `garden tool capture --from <script>` (`/garden-tool`) — generalizes a one-off script
  (lifts hardcoded values into flags, strips secrets, adds `--help`, targets your
  runtime) and stages it under `tool-proposals/` for review. Never installed
  until gated. `--dry-run` previews; `--runtime bash|uv|node` overrides the
  default.
- `garden tool gate` (`/garden-tool-gate`) — review staged tools and accept or
  reject: `list` / `show <name>` (manifest + full source) / `review <name>`
  (static safety check) / `accept` / `reject --note`. You must read the code;
  accept promotes the tool and records to `wiki/tool-impact.jsonl`. `--scope
  global` (default) installs `<prefix><name>` onto `~/.local/bin` and refreshes
  the catalog; `--scope project [--project-dir <repo>]` stages it under the
  repo's `.claude/` instead. `--no-install` skips the PATH install.
- `garden tool mine` (`/garden-tool-mine`) — scan traces for recurring/reusable
  commands and stage them as tool proposals automatically (the ambient path).
- `garden tool catalog` — regenerate the `wiki-garden-tools` catalog skill from
  installed tools (auto-runs on accept) so the agent discovers and reuses them.
- Config in `~/.config/wiki-garden/config`: `tool_prefix` (default `gt-`),
  `tool_runtime` (default `bash`), and `tool_guidance` (short house-style note).
- House-style overlays in `~/.config/wiki-garden/prompts/`: `tool.md` (always)
  and `tool.<runtime>.md` (per runtime) are appended to the generalizer, so you
  can dictate conventions — e.g. "uv scripts with PEP 723 + pinned deps, click
  for args" or "bash with `set -euo pipefail` + getopts". Safety rules still win.

## Status

The full loop works end to end: trace capture (`/wiki-garden`), consolidation
(`garden maintain`), skill proposal (`garden propose`), the human gate
(`garden gate`), the `evolve` sequencer, the tools layer (`capture` / `mine` /
`gate` / `catalog`), the `garden tend` web UI, and global-vs-project scoping.
Still open: the automatic session-end capture hook and a scheduled evolve run.
See [DESIGN.md](DESIGN.md) build phases for the details.
