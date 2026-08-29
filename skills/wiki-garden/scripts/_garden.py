"""Shared helpers for Wiki Garden standalone runners (store resolution + pluggable
LLM backend + JSON parsing). Imported by garden-maintain and garden-propose.

Not executable and not on PATH; runners add their *resolved* dir to sys.path so
this is importable even when the runner is invoked via a PATH symlink.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path


def log(msg: str) -> None:
    print(f"[wiki-garden] {msg}", file=sys.stderr)


def die(msg: str, code: int = 1):
    log(msg)
    sys.exit(code)


# ---------------------------------------------------------------- store

def resolve_store(here: Path) -> Path:
    """Resolve the store via garden-home (PATH or sibling), else env/default."""
    for cand in ("garden-home", str(here / "garden-home")):
        try:
            out = subprocess.run([cand], capture_output=True, text=True, check=True)
            return Path(out.stdout.strip())
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    env = os.environ.get("WIKIGARDEN_HOME")
    return Path(env) if env else Path.home() / ".config" / "wiki-garden"


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
    model does only our transform; the user content is piped via stdin."""
    cmd = ["claude", "-p", "--system-prompt", system]
    if model:
        cmd += ["--model", model]
    try:
        out = subprocess.run(cmd, input=user, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError("`claude` CLI not found on PATH (needed for WIKIGARDEN_LLM=claude)")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"claude -p failed: {e.stderr.strip() or e}")
    return out.stdout


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


def write_tools_catalog(store: Path) -> dict:
    """(Re)generate the tools catalog from <store>/tools/*/TOOL.md — a
    Runme-compatible markdown doc at <store>/tools/CATALOG.md and a discoverable
    `wiki-garden-tools` skill at ~/.claude/skills/wiki-garden-tools/SKILL.md so
    an agent reaches for installed tools instead of rewriting them."""
    tdir = store / "tools"
    tools = []
    if tdir.exists():
        for d in sorted(p for p in tdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            tm = d / "TOOL.md"
            if tm.exists():
                fm = parse_frontmatter(tm.read_text())
                if fm.get("name"):
                    tools.append(fm)

    skill_dir = Path.home() / ".claude" / "skills" / "wiki-garden-tools"
    if not tools:
        # nothing to advertise: drop a stale catalog skill, keep an empty note
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "CATALOG.md").write_text("# Your Wiki Garden Tools\n\n(none yet)\n")
        return {"count": 0, "names": []}

    names = [t["name"] for t in tools]
    body = ["# Your Wiki Garden Tools", "",
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

    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "CATALOG.md").write_text(catalog)

    desc = ("Your installed Wiki Garden CLI tools — prefer these over rewriting a "
            f"script. Available: {', '.join(names)}. Use when a task matches one of "
            "these tools; run `<tool> --help` first.")
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: wiki-garden-tools\ndescription: {desc}\n---\n\n{catalog}")
    return {"count": len(tools), "names": names}


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
