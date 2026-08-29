"""_web — the `garden tend` local web UI: a stdlib-only HTTP server that reads the
Wiki Garden store and drives the gates from the browser.

Deliberately dependency-free (only the Python standard library) so it runs on the
same interpreter as everything else — including the older system Python an
end-user who installed via `npx skills add` might have. The read side parses the
store's files directly; every mutation (accept/reject a skill proposal or a tool)
calls the in-process gate functions in `_skills` / `_tools`, so the gating logic
(retro-eval, the impact ledger, install) stays single-sourced with the CLI.

The compiled Svelte front-end (see repo-root `web/`, built into the sibling
`web-dist/`) is served as static files with SPA fallback. API lives under /api.
"""
from __future__ import annotations

import io
import json
import mimetypes
import shutil
import subprocess
import sys
import threading
import webbrowser
from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import _garden
import _skills
import _tools

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / "web-dist"          # compiled front-end, shipped in the skill
META = {"proposal.json", "PURPOSE.md", "SKILL.md", "TOOL.md"}


# ------------------------------------------------------------------ store reads
# Each reader returns plain JSON-able dicts/lists. They tolerate a missing or
# half-populated store (fresh install, empty sub-dirs) by returning empties.

def _read(p: Path) -> str:
    try:
        return p.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _parse_gate(purpose: str) -> dict:
    """Pull the `gate: human=.. retro=..` / `review=..` line out of PURPOSE.md."""
    out = {}
    for ln in purpose.splitlines():
        if ln.startswith("gate:"):
            for tok in ln[len("gate:"):].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    out[k] = v
    return out


def read_proposals(st: Path) -> list[dict]:
    root = st / "proposals"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.glob("*")):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            prop = json.loads(_read(d / "proposal.json") or "{}")
        except json.JSONDecodeError:
            prop = {}
        purpose = _read(d / "PURPOSE.md")
        out.append({
            "id": d.name,
            "skill_name": prop.get("skill_name", d.name.split("_", 1)[-1]),
            "pattern": prop.get("pattern", ""),
            "rationale": prop.get("rationale", "").strip(),
            "report": prop.get("report", "").strip(),
            "skill_md": prop.get("skill_md") or _read(d / "SKILL.md"),
            "purpose": purpose,
            "gate": _parse_gate(purpose),
            "staged_at": _iso(d.stat().st_mtime),
        })
    return out


def read_tools(st: Path) -> list[dict]:
    root = st / "tool-proposals"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.glob("*")):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            prop = json.loads(_read(d / "proposal.json") or "{}")
        except json.JSONDecodeError:
            prop = {}
        # the executable is the single non-meta file staged beside the manifests
        exe = next((f for f in sorted(d.glob("*")) if f.is_file() and f.name not in META), None)
        purpose = _read(d / "PURPOSE.md")
        out.append({
            "id": d.name,
            "name": prop.get("name", d.name.split("_", 1)[-1]),
            "runtime": prop.get("runtime", ""),
            "description": prop.get("description", "").strip(),
            "tool_md": _read(d / "TOOL.md"),
            "purpose": purpose,
            "gate": _parse_gate(purpose),
            "exe_name": exe.name if exe else None,
            "source": _read(exe) if exe else "",
            "staged_at": _iso(d.stat().st_mtime),
        })
    return out


def read_patterns(st: Path) -> list[dict]:
    root = st / "wiki" / "patterns"
    if not root.is_dir():
        return []
    out = []
    for f in sorted(root.glob("*.md")):
        body = _read(f)
        title = next((ln.lstrip("# ").strip() for ln in body.splitlines()
                      if ln.startswith("#")), f.stem)
        out.append({"id": f.stem, "title": title, "body": body,
                    "updated_at": _iso(f.stat().st_mtime)})
    return out


def read_traces(st: Path) -> list[dict]:
    root = st / "raw"
    if not root.is_dir():
        return []
    out = []
    for f in sorted(root.glob("*.md"), reverse=True):
        out.append({"id": f.stem, "body": _read(f), "captured_at": _iso(f.stat().st_mtime)})
    return out


def read_skills(st: Path) -> list[dict]:
    root = st / "skills"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.glob("*")):
        if not d.is_dir() or d.name.startswith("."):
            continue
        fm = _garden.parse_frontmatter(_read(d / "SKILL.md"))
        out.append({"id": d.name, "name": fm.get("name", d.name),
                    "description": fm.get("description", ""),
                    "activated_at": _iso(d.stat().st_mtime)})
    return out


def _read_jsonl(p: Path) -> list[dict]:
    rows = []
    for ln in _read(p).splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def read_ledger(st: Path) -> dict:
    return {"skills": _read_jsonl(st / "wiki" / "skill-impact.jsonl"),
            "tools": _read_jsonl(st / "wiki" / "tool-impact.jsonl")}


def read_evolution(st: Path) -> str:
    return _read(st / "wiki" / "evolution-log.md")


def pick_folder(start: str = "") -> dict:
    """Pop a NATIVE OS folder chooser on the machine running the server and return
    the chosen absolute path. The server is local, so the dialog appears for the
    user. macOS uses osascript; Linux falls back to zenity/kdialog. Returns
    {ok:False, reason:"unsupported"} where no dialog tool exists — the UI then
    keeps its text field. A user cancel returns {ok:False, canceled:True}."""
    start = (start or "").strip()

    if sys.platform == "darwin":
        default = f'default location POSIX file "{start}"' if start else ""
        script = f'POSIX path of (choose folder with prompt "Select project repo" {default})'
        try:
            out = subprocess.run(["osascript", "-e", script],
                                 capture_output=True, text=True)
        except FileNotFoundError:
            return {"ok": False, "reason": "unsupported"}
        if out.returncode != 0:
            # -128 is the AppleScript "user canceled" code.
            if "-128" in (out.stderr or "") or "User canceled" in (out.stderr or ""):
                return {"ok": False, "canceled": True}
            return {"ok": False, "reason": (out.stderr or "dialog failed").strip()}
        return {"ok": True, "path": out.stdout.strip().rstrip("/") or "/"}

    # Linux: try zenity, then kdialog.
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=Select project repo"]
        if start:
            cmd.append(f"--filename={start}/")
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--getexistingdirectory", start or "."]
    else:
        return {"ok": False, "reason": "unsupported"}
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return {"ok": False, "canceled": True}
    return {"ok": True, "path": out.stdout.strip().rstrip("/") or "/"}


def validate_project(path: str) -> dict:
    """Check a candidate project dir for project-scoped accepts. Reports whether
    it exists and whether it's a git repo (project skills land in .claude/skills
    there, which is most useful when the repo is version-controlled)."""
    raw = (path or "").strip()
    if not raw:
        return {"ok": False, "reason": "empty"}
    p = Path(raw).expanduser()
    if not p.is_dir():
        return {"ok": False, "reason": "not a directory", "path": str(p)}
    is_git = (p / ".git").exists()
    return {"ok": True, "path": str(p.resolve()), "git": is_git,
            "reason": "ok" if is_git else "not a git repo (project skill still installs)"}


def snapshot(st: Path) -> dict:
    """Everything the UI needs in one shot (also lets the client render offline)."""
    props = read_proposals(st)
    tools = read_tools(st)
    patterns = read_patterns(st)
    traces = read_traces(st)
    skills = read_skills(st)
    return {
        "store": str(st),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"proposals": len(props), "tools": len(tools),
                   "patterns": len(patterns), "traces": len(traces), "skills": len(skills)},
        "proposals": props,
        "tools": tools,
        "patterns": patterns,
        "traces": traces,
        "skills": skills,
        "evolution": read_evolution(st),
        "ledger": read_ledger(st),
    }


# ------------------------------------------------------------------ mutations
# Reuse the exact gate paths the CLI uses. They print (captured) and may call
# _garden.die() -> SystemExit on a bad request; we translate that into an error
# payload rather than tearing down the server.

def _run_gate(fn, *args, **kwargs) -> dict:
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            result = fn(*args, **kwargs)
    except SystemExit as e:
        return {"ok": False, "error": str(e) or "gate rejected the request", "log": buf.getvalue()}
    except Exception as e:  # keep the server alive; surface the failure to the UI
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "log": buf.getvalue()}
    out = {"ok": True, "log": buf.getvalue()}
    if isinstance(result, dict):
        out["result"] = result
    return out


def accept_proposal(name: str, body: dict) -> dict:
    return _run_gate(_skills.gate_accept, name,
                     body.get("note", ""), bool(body.get("no_install", False)),
                     body.get("scope", "global"), body.get("project_dir"),
                     body.get("backend", "claude"), body.get("model"))


def reject_proposal(name: str, body: dict) -> dict:
    return _run_gate(_skills.gate_reject, name, body.get("note", ""),
                     bool(body.get("retro", False)),
                     body.get("backend", "claude"), body.get("model"))


def accept_tool(name: str, body: dict) -> dict:
    return _run_gate(_tools.tool_gate_accept, name,
                     body.get("note", ""), bool(body.get("no_install", False)),
                     body.get("scope", "global"), body.get("project_dir"),
                     body.get("backend", "claude"), body.get("model"))


def reject_tool(name: str, body: dict) -> dict:
    return _run_gate(_tools.tool_gate_reject, name, body.get("note", ""),
                     bool(body.get("review", False)),
                     body.get("backend", "claude"), body.get("model"))


# ------------------------------------------------------------------ http

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):  # quiet by default; the runner prints the URL
        pass

    # -- helpers --
    def _send_json(self, obj, status=200):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, ValueError):
            return {}

    def _store(self) -> Path:
        return _garden.store_root()

    # -- routing --
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/snapshot":
            return self._send_json(snapshot(self._store()))
        if path == "/api/health":
            return self._send_json({"ok": True})
        if path == "/api/validate-project":
            q = parse_qs(parsed.query)
            return self._send_json(validate_project((q.get("path") or [""])[0]))
        if path.startswith("/api/"):
            return self._send_json({"error": "not found"}, 404)
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/pick-project":
            body = self._read_body()
            return self._send_json(pick_folder(body.get("start", "")))
        parts = [p for p in path.split("/") if p]  # ['api','proposals','<name>','accept']
        if len(parts) == 4 and parts[0] == "api" and parts[3] in ("accept", "reject"):
            name = unquote(parts[2])
            body = self._read_body()
            table = {
                ("proposals", "accept"): accept_proposal,
                ("proposals", "reject"): reject_proposal,
                ("tools", "accept"): accept_tool,
                ("tools", "reject"): reject_tool,
            }
            fn = table.get((parts[1], parts[3]))
            if fn:
                res = fn(name, body)
                return self._send_json(res, 200 if res.get("ok") else 400)
        return self._send_json({"error": "not found"}, 404)

    # -- static (compiled front-end, SPA fallback) --
    def _serve_static(self, path: str):
        if not DIST.is_dir():
            return self._send_json(
                {"error": "web-dist not built", "hint": "run `bun run build` in web/"}, 503)
        rel = unquote(path.lstrip("/")) or "index.html"
        target = (DIST / rel).resolve()
        if DIST not in target.parents and target != DIST:
            target = DIST / "index.html"          # escape attempt -> app shell
        if not target.is_file():
            target = DIST / "index.html"          # SPA fallback
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    """Boot the tend server. Blocks until Ctrl-C."""
    st = _garden.store_root()
    _garden.ensure_skeleton(st)
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"[wiki-garden] tending {st}")
    print(f"[wiki-garden] serving {url}  (Ctrl-C to stop)")
    if not DIST.is_dir():
        print("[wiki-garden] note: web-dist/ not found — build the UI with `bun run build` in web/")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[wiki-garden] stopped")
    finally:
        httpd.server_close()
