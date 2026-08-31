"""garden — Wiki Garden CLI. Compiles coding-session experience into a persistent
wiki plus evolving skills and tools.

  garden init                                   # set up store, versioning, config
  garden home
  garden maintain | propose | evolve            [--dry-run]
  garden gate     list | show | retro | accept | reject
  garden tool     capture | mine | catalog
  garden tool     gate  list | show | review | accept | reject

Backend is pluggable via --backend / $WIKIGARDEN_LLM (claude|anthropic|openai);
default `claude` uses the local Claude Code login (no key).
"""
from __future__ import annotations

import shutil
from typing import Optional

import typer

from . import _garden
from . import _skills
from . import _tools
from . import _web

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="Wiki Garden — compile session experience into skills + tools.")

BACKEND = typer.Option("claude", "--backend", envvar="WIKIGARDEN_LLM",
                       help="LLM backend: claude | anthropic | openai")
MODEL = typer.Option(None, "--model", envvar="WIKIGARDEN_LLM_MODEL", help="Model id for the backend")
DRY = typer.Option(False, "--dry-run", help="Do everything except write")
SCOPE = typer.Option("global", "--scope", help="Install scope: global | project")
PROJECT = typer.Option(None, "--project-dir", help="Repo for project scope (default: cwd git root)")


@app.command()
def home():
    """Print the resolved store path."""
    print(_garden.store_root())


@app.command()
def init(yes: bool = typer.Option(False, "--yes", "-y", help="Accept defaults, no prompts")):
    """Set up the store: skeleton, config, git versioning, eval seeds, next steps."""
    store = _garden.store_root()  # also ensures the skeleton
    typer.secho(f"Wiki Garden store: {store}", bold=True)
    typer.echo("  ✓ skeleton ready (raw, wiki, skills, tools, proposals, eval)")

    # --- config: backend + model ---
    cfg = _garden.read_config()
    if yes:
        backend = cfg.get("backend", "claude")
        model = cfg.get("model")
    else:
        backend = typer.prompt("LLM backend (claude|anthropic|openai)",
                               default=cfg.get("backend", "claude"))
        model = typer.prompt("Model id (blank = backend default)",
                             default=cfg.get("model", ""), show_default=False) or None
    updates = {"backend": backend}
    if model:
        updates["model"] = model

    # --- install targets: which agents get accepted skills ---
    # claude-code is native (a ~/.claude/skills symlink); other agents (codex,
    # cursor, opencode, pi, …) are installed via `npx skills` at the gate.
    if yes:
        targets = cfg.get("install_targets", "claude-code")
    else:
        targets = typer.prompt(
            "Install accepted skills to which agents "
            "(comma list: claude-code,codex,cursor,opencode | none)",
            default=cfg.get("install_targets", "claude-code"))
    updates["install_targets"] = targets.strip()

    if str(store) != str(_garden.config_file().parent):
        updates["home"] = str(store)
    _garden.set_config(updates)
    typer.echo(f"  ✓ config written ({_garden.config_file()})")

    # --- git versioning (opt-in) ---
    if _garden.is_git_store(store):
        typer.echo("  ✓ git versioning already on")
    elif not shutil.which("git"):
        typer.secho("  • git not found on PATH — skipping versioning", fg="yellow")
    elif yes or typer.confirm("Version the store with git (commit on every gate action)?", default=True):
        if _garden.git_init_store(store):
            typer.echo("  ✓ git initialised — gate actions will commit from now on")
        else:
            typer.secho("  • could not initialise git", fg="yellow")

    # --- seed eval stash ---
    stash = store / "eval" / "stash"
    have = len(list(stash.glob("*.md"))) if stash.exists() else 0
    if have:
        typer.echo(f"  ✓ eval stash has {have} past-task case(s)")
    else:
        typer.secho("  • eval/stash is empty — retro-eval will be skipped at the gate.", fg="yellow")
        typer.echo(f"    Drop past-task markdown files into {stash} to enable retro-eval.")

    typer.secho("\nNext:", bold=True)
    typer.echo("  1. Capture sessions:  /wiki-garden  (or `garden` maintain on raw traces)")
    typer.echo("  2. Evolve:            garden evolve      # maintain wiki + stage a skill")
    typer.echo("  3. Review the gate:   garden tend        # browser UI, or `garden gate list`")


@app.command()
def tend(host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
         port: int = typer.Option(8787, "--port", help="Port"),
         no_open: bool = typer.Option(False, "--no-open", help="Don't open a browser")):
    """Open the local web UI to browse and tend the garden (accept/reject in a browser)."""
    _web.serve(host, port, open_browser=not no_open)


@app.command()
def maintain(dry_run: bool = DRY, plan_file: Optional[str] = typer.Option(None, "--plan-file"),
             backend: str = BACKEND, model: Optional[str] = MODEL):
    """Compile new traces into wiki/patterns."""
    _skills.maintain(dry_run, plan_file, backend, model)


@app.command()
def propose(dry_run: bool = DRY, plan_file: Optional[str] = typer.Option(None, "--plan-file"),
            backend: str = BACKEND, model: Optional[str] = MODEL):
    """Stage one atomic skill proposal from the wiki."""
    _skills.propose(dry_run, plan_file, backend, model)


@app.command()
def evolve(dry_run: bool = DRY, backend: str = BACKEND, model: Optional[str] = MODEL):
    """One iteration: maintain, then propose."""
    _skills.maintain(dry_run, None, backend, model)
    _skills.propose(dry_run, None, backend, model)


# ---- gate (skills) ----
gate = typer.Typer(no_args_is_help=True, help="Review/accept/reject staged skill proposals.")
app.add_typer(gate, name="gate")


@gate.command("list")
def gate_list():
    """List staged skill proposals."""
    _skills.gate_list()


@gate.command("show")
def gate_show(name: str):
    """Print a proposal (PURPOSE.md + SKILL.md)."""
    _skills.gate_show(name)


@gate.command("retro")
def gate_retro(name: str, backend: str = BACKEND, model: Optional[str] = MODEL):
    """Run retro-eval on a proposal."""
    _skills.gate_retro(name, backend, model)


@gate.command("accept")
def gate_accept(name: str, note: str = typer.Option("", "--note"),
                no_install: bool = typer.Option(False, "--no-install"),
                scope: str = SCOPE, project_dir: Optional[str] = PROJECT,
                backend: str = BACKEND, model: Optional[str] = MODEL):
    """Accept a proposal -> skills/ (+ install)."""
    _skills.gate_accept(name, note, no_install, scope, project_dir, backend, model)


@gate.command("reject")
def gate_reject(name: str, note: str = typer.Option("", "--note"),
                retro: bool = typer.Option(False, "--retro"),
                backend: str = BACKEND, model: Optional[str] = MODEL):
    """Reject a proposal (recorded, never re-proposed)."""
    _skills.gate_reject(name, note, retro, backend, model)


# ---- tool ----
tool = typer.Typer(no_args_is_help=True, help="Tools layer: capture/mine/catalog/gate.")
app.add_typer(tool, name="tool")


@tool.command("capture")
def tool_capture(from_: Optional[str] = typer.Option(None, "--from", help="raw script path (else stdin)"),
                 name: Optional[str] = typer.Option(None, "--name"),
                 runtime: Optional[str] = typer.Option(None, "--runtime", help="bash|uv|node"),
                 dry_run: bool = DRY, plan_file: Optional[str] = typer.Option(None, "--plan-file"),
                 backend: str = BACKEND, model: Optional[str] = MODEL):
    """Turn a raw script into a staged reusable tool."""
    _tools.capture(from_, name, runtime, dry_run, plan_file, backend, model)


@tool.command("mine")
def tool_mine(dry_run: bool = DRY, backend: str = BACKEND, model: Optional[str] = MODEL):
    """Mine traces for recurring commands and stage them as tools."""
    _tools.mine(dry_run, backend, model)


@tool.command("catalog")
def tool_catalog():
    """Regenerate the wiki-garden-tools catalog skill."""
    _tools.catalog()


# ---- tool gate ----
tgate = typer.Typer(no_args_is_help=True, help="Review/accept/reject staged tools.")
tool.add_typer(tgate, name="gate")


@tgate.command("list")
def tg_list():
    """List staged tools."""
    _tools.tool_gate_list()


@tgate.command("show")
def tg_show(name: str):
    """Print a tool's manifest + full source."""
    _tools.tool_gate_show(name)


@tgate.command("review")
def tg_review(name: str, backend: str = BACKEND, model: Optional[str] = MODEL):
    """Static safety review of a staged tool."""
    _tools.tool_gate_review(name, backend, model)


@tgate.command("accept")
def tg_accept(name: str, note: str = typer.Option("", "--note"),
              no_install: bool = typer.Option(False, "--no-install"),
              scope: str = SCOPE, project_dir: Optional[str] = PROJECT,
              backend: str = BACKEND, model: Optional[str] = MODEL):
    """Accept a tool -> tools/ + install on PATH."""
    _tools.tool_gate_accept(name, note, no_install, scope, project_dir, backend, model)


@tgate.command("reject")
def tg_reject(name: str, note: str = typer.Option("", "--note"),
              review: bool = typer.Option(False, "--review"),
              backend: str = BACKEND, model: Optional[str] = MODEL):
    """Reject a staged tool (recorded, archived)."""
    _tools.tool_gate_reject(name, note, review, backend, model)


def main() -> None:
    """Console-script entry point (see [project.scripts] in pyproject.toml)."""
    app()


if __name__ == "__main__":
    main()
