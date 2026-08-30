"""Shared helpers for Wiki Garden standalone runners (store resolution + pluggable
LLM backend + JSON parsing). Imported by garden-maintain and garden-propose.

Not executable and not on PATH; runners add their *resolved* dir to sys.path so
this is importable even when the runner is invoked via a PATH symlink.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def prompt(name: str) -> str:
    """Read a shipped prompt (prompts/<name>.md)."""
    return (PROMPTS / f"{name}.md").read_text()


def log(msg: str) -> None:
    print(f"[wiki-garden] {msg}", file=sys.stderr)


def die(msg: str, code: int = 1):
    log(msg)
    sys.exit(code)


# ---------------------------------------------------------------- store

def store_root() -> Path:
    """Resolve the store root: $WIKIGARDEN_HOME -> config `home=` -> default
    ~/.config/wiki-garden. Ensures the skeleton exists. Pure Python (no subprocess)."""
    env = os.environ.get("WIKIGARDEN_HOME")
    if env:
        root = Path(env).expanduser()
    else:
        home = read_config().get("home")
        root = Path(home).expanduser() if home else config_file().parent
    ensure_skeleton(root)
    return root


def ensure_skeleton(root: Path) -> None:
    for d in ("raw", "wiki/patterns", "skills", "proposals", "tools",
              "tool-proposals", "eval/stash", "eval/results"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "wiki" / ".processed.log").touch()
    si = root / "wiki" / "skill-impact.jsonl"
    if not si.exists():
        si.write_text("")
    el = root / "wiki" / "evolution-log.md"
    if not el.exists():
        el.write_text("# Evolution Log\n\n<!-- newest first -->\n")


def resolve_store(here: Path | None = None) -> Path:
    """Back-compat alias for store_root() (the `here` arg is ignored)."""
    return store_root()


def config_file() -> Path:
    """The machine-local config file garden-home also reads (home=, tool_*=)."""
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "wiki-garden" / "config"


def read_config() -> dict:
    cfg = {}
    f = config_file()
    if f.exists():
        for ln in f.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def config_get(key: str, default: str = "") -> str:
    return read_config().get(key, default)


def set_config(updates: dict) -> Path:
    """Merge key=value updates into the machine-local config file, preserving
    existing keys. Returns the config path."""
    cfg = read_config()
    cfg.update({k: v for k, v in updates.items() if v is not None})
    f = config_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{k}={v}" for k, v in cfg.items())
    f.write_text(body + "\n" if body else "")
    return f


def tool_settings() -> tuple[str, str]:
    """(tool_prefix, tool_runtime) from config, with defaults."""
    c = read_config()
    return c.get("tool_prefix", "gt-"), c.get("tool_runtime", "bash")


def prompt_overlays(names: list[str]) -> str:
    """Concatenate user prompt-overlay files from <config>/prompts/<name>.md for
    each name (missing files skipped). Lets a user inject house style/runtime
    conventions into an agent's prompt without editing the shipped prompts."""
    base = config_file().parent / "prompts"
    parts = []
    for n in names:
        f = base / f"{n}.md"
        if f.exists():
            txt = f.read_text().strip()
            if txt:
                parts.append(txt)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- llm

def call_llm(system: str, user: str, backend: str, model: str | None) -> str:
    if backend == "claude":
        return _claude_cli(system, user, model)
    if backend == "anthropic":
        return _anthropic(system, user, model)
    if backend == "openai":
        return _openai(system, user, model)
    die(f"unknown backend '{backend}' (use claude|anthropic|openai)")


def _claude_cli(system: str, user: str, model: str | None) -> str:
    """Use the local `claude` CLI in headless mode — no API key, uses the
    existing Claude Code login. System prompt is replaced (not appended) so the
    model does only our transform; the user content is piped via stdin.

    Runs with `--output-format stream-json` so the model's output can be
    surfaced token-by-token: when WIKIGARDEN_STREAM=1 (which `garden tend` sets
    when it spawns a producer under its pty) each text delta is echoed to stderr
    so it flows to the tend panel live. Either way the authoritative final text
    comes from the terminal `result` event, so callers get exactly what the old
    plain-text mode returned. `--no-session-persistence` keeps these one-shot
    transforms out of the user's session history."""
    stream = os.environ.get("WIKIGARDEN_STREAM") == "1"
    cmd = ["claude", "-p", "--system-prompt", system,
           "--output-format", "stream-json", "--verbose",
           "--include-partial-messages", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except FileNotFoundError:
        raise RuntimeError("`claude` CLI not found on PATH (needed for WIKIGARDEN_LLM=claude)")

    # Feed stdin from a thread so a large prompt can't deadlock against the
    # model's output filling the stdout pipe before stdin is fully drained.
    def _feed():
        try:
            proc.stdin.write(user)
        except BrokenPipeError:
            pass
        finally:
            proc.stdin.close()

    writer = threading.Thread(target=_feed, daemon=True)
    writer.start()

    result: str | None = None
    err_msg: str | None = None
    parts: list[str] = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue  # non-JSON diagnostics — ignore
        etype = ev.get("type")
        if etype == "stream_event":
            inner = ev.get("event") or {}
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    parts.append(text)
                    if stream and text:
                        sys.stderr.write(text)
                        sys.stderr.flush()
        elif etype == "result":
            if ev.get("is_error"):
                err_msg = ev.get("result") or ev.get("error") or "claude reported an error"
            elif ev.get("result") is not None:
                result = ev.get("result")
    proc.wait()
    writer.join(timeout=1)
    if stream:
        sys.stderr.write("\n")  # terminate the streamed line
        sys.stderr.flush()
    if err_msg:
        raise RuntimeError(f"claude -p failed: {err_msg}")
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exited with status {proc.returncode}")
    return result if result is not None else "".join(parts)


def _http_json(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _anthropic(system: str, user: str, model: str | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    model = model or "claude-opus-4-8"
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01",
         "content-type": "application/json"},
        {"model": model, "max_tokens": 8000, "system": system,
         "messages": [{"role": "user", "content": user}]},
    )
    return "".join(b.get("text", "") for b in data.get("content", []))


def _openai(system: str, user: str, model: str | None) -> str:
    base = os.environ.get("WIKIGARDEN_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "")
    model = model or os.environ.get("WIKIGARDEN_LLM_MODEL") or "gpt-4o"
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    data = _http_json(
        f"{base}/chat/completions", headers,
        {"model": model, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}]},
    )
    return data["choices"][0]["message"]["content"]


def parse_frontmatter(text: str) -> dict:
    """Parse a simple top-level `key: value` YAML frontmatter block."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end] if end > 0 else ""
    d = {}
    for ln in block.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and ":" in ln and not ln.startswith(" "):
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


# ---------------------------------------------------------------- git versioning
# Opt-in: the store is versioned only after `garden init` runs `git init` on it.
# ensure_skeleton never touches git, so existing stores are left alone until the
# user chooses. When the store IS a repo, gate actions commit so every
# accept/reject/edit has a diff and history.

def is_git_store(store: Path) -> bool:
    return (store / ".git").is_dir()


def _git(store: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(store), *args],
                          capture_output=True, text=True)


def git_init_store(store: Path) -> bool:
    """Initialise the store as a git repo for versioning (idempotent). Returns
    True if the store is a repo afterwards, False if git is unavailable."""
    if is_git_store(store):
        return True
    if not shutil.which("git"):
        return False
    if _git(store, "init", "-q").returncode != 0:
        return False
    gi = store / ".gitignore"
    if not gi.exists():
        gi.write_text("# transient retro-eval output — regenerated each run\neval/results/\n")
    git_commit(store, "wiki-garden: initialise store")
    return True


def git_commit(store: Path, message: str) -> bool:
    """Stage everything and commit, if the store is a repo with staged changes.
    Uses an inline identity so it works even without a configured git user."""
    if not is_git_store(store) or not shutil.which("git"):
        return False
    _git(store, "add", "-A")
    if _git(store, "diff", "--cached", "--quiet").returncode == 0:
        return False  # nothing changed
    r = _git(store, "-c", "user.name=Wiki Garden",
             "-c", "user.email=wiki-garden@localhost", "commit", "-q", "-m", message)
    return r.returncode == 0


# ---------------------------------------------------------------- frontmatter versioning

def get_version(text: str) -> int:
    """The integer `version:` from a SKILL.md/TOOL.md frontmatter, or 0 if unset."""
    try:
        return int(parse_frontmatter(text).get("version", ""))
    except (TypeError, ValueError):
        return 0


def set_version(text: str, version: int) -> str:
    """Return the doc with `version: <n>` set in its frontmatter (added after
    `name:` if absent). No-op when there is no frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        return text
    fm = lines[1:close]
    for i, ln in enumerate(fm):
        if re.match(r"\s*version\s*:", ln):
            fm[i] = f"version: {version}"
            break
    else:
        idx = next((i + 1 for i, ln in enumerate(fm) if ln.startswith("name:")), len(fm))
        fm.insert(idx, f"version: {version}")
    result = "\n".join(["---", *fm, "---", *lines[close + 1:]])
    return result + "\n" if text.endswith("\n") else result


def resolve_project_dir(explicit: str | None = None) -> Path:
    """The repo to scope project outputs into: --project-dir, else cwd's git
    toplevel. Errors if neither is available."""
    if explicit:
        return Path(explicit).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError):
        die("not in a git repo — pass --project-dir <path> for project scope")


def build_catalog(tools_root: Path, catalog_path: Path, skill_dir: Path,
                  scope_label: str) -> dict:
    """Scan tools_root/*/TOOL.md and (re)write catalog_path + a wiki-garden-tools
    SKILL.md into skill_dir. Used for both the global store and a project's
    .claude. Removes a stale skill when there are no tools."""
    tools = []
    if tools_root.exists():
        for d in sorted(p for p in tools_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            tm = d / "TOOL.md"
            if tm.exists():
                fm = parse_frontmatter(tm.read_text())
                if fm.get("name"):
                    tools.append(fm)
    if not tools:
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text("# Your Wiki Garden Tools\n\n(none yet)\n")
        return {"count": 0, "names": []}

    names = [t["name"] for t in tools]
    body = [f"# Your Wiki Garden Tools ({scope_label})", "",
            "Reusable commands installed on your PATH. **Prefer these over writing a",
            "new one-off script.** Run `<tool> --help` for details.", ""]
    for t in tools:
        body += [f"## {t['name']}", "", t.get("description", "").strip(), ""]
        if t.get("usage"):
            body.append(f"Usage: `{t['usage'].strip()}`  ")
        if t.get("deps"):
            body.append(f"Requires: {t['deps'].strip()}  ")
        body += ["", f'```sh {{"name":"{t["name"]}"}}', f"{t['name']} --help", "```", ""]
    catalog = "\n".join(body)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog)

    desc = ("Your installed Wiki Garden CLI tools — prefer these over rewriting a "
            f"script. Available: {', '.join(names)}. Use when a task matches one of "
            "these tools; run `<tool> --help` first.")
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: wiki-garden-tools\ndescription: {desc}\n---\n\n{catalog}")
    return {"count": len(tools), "names": names}


def write_tools_catalog(store: Path) -> dict:
    """Regenerate the GLOBAL tools catalog (from <store>/tools) into the global
    wiki-garden-tools skill."""
    return build_catalog(store / "tools", store / "tools" / "CATALOG.md",
                         Path.home() / ".claude" / "skills" / "wiki-garden-tools",
                         "global")


def write_project_tools_catalog(project_dir: Path) -> dict:
    """Regenerate a PROJECT tools catalog from <repo>/.claude/wiki-garden-tools
    into the repo's own wiki-garden-tools skill (committable)."""
    root = project_dir / ".claude" / "wiki-garden-tools"
    return build_catalog(root, root / "CATALOG.md",
                         project_dir / ".claude" / "skills" / "wiki-garden-tools",
                         "project")


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            die("LLM did not return JSON")
        return json.loads(m.group(0))
