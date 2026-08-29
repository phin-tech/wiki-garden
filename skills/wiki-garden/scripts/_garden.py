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
        die("`claude` CLI not found on PATH (needed for WIKIGARDEN_LLM=claude)")
    except subprocess.CalledProcessError as e:
        die(f"claude -p failed: {e.stderr.strip() or e}")
    return out.stdout


def _http_json(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _anthropic(system: str, user: str, model: str | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or die("ANTHROPIC_API_KEY not set")
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
