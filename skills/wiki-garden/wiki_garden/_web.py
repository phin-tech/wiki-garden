"""_web — the `garden tend` local web UI: a stdlib-only HTTP server that reads the
Wiki Garden store and drives the gates from the browser.

Deliberately stdlib-only — no web framework. The `garden` CLI runs under uv
(PEP 723, Python >=3.11), so this isn't about supporting an old system Python;
it's that a threaded stdlib server is a clean fit for what this does (read the
store, drive the gates, stream a subprocess) and keeps the runtime a small,
forkable script. The read side parses the store's files directly; every mutation
(accept/reject a skill proposal or a tool) calls the in-process gate functions in
`_skills` / `_tools`, so the gating logic (retro-eval, the impact ledger, install)
stays single-sourced with the CLI. Producer output streams over SSE from a pty
(see the streaming-producers section).

The compiled Svelte front-end (see repo-root `web/`, built into the sibling
`web-dist/`) is served as static files with SPA fallback. API lives under /api.
"""
from __future__ import annotations

import errno
import io
import json
import mimetypes
import os
import pty
import re
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import _garden
from . import _skills
from . import _tools

HERE = Path(__file__).resolve().parent
DIST = HERE / "web-dist"                 # compiled front-end, shipped in the package
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


def _parse_proposal(d: Path, status: str) -> dict:
    try:
        prop = json.loads(_read(d / "proposal.json") or "{}")
    except json.JSONDecodeError:
        prop = {}
    purpose = _read(d / "PURPOSE.md")
    gate = _parse_gate(purpose)
    # Archived proposals keep the PURPOSE.md they were staged with (gate still
    # says pending); trust the folder they now live in for the human verdict.
    if status == "rejected":
        gate["human"] = "rejected"
    return {
        "id": d.name,
        "status": status,
        "skill_name": prop.get("skill_name", d.name.split("_", 1)[-1]),
        "pattern": prop.get("pattern", ""),
        "rationale": prop.get("rationale", "").strip(),
        "report": prop.get("report", "").strip(),
        "skill_md": prop.get("skill_md") or _read(d / "SKILL.md"),
        "purpose": purpose,
        "gate": gate,
        "staged_at": _iso(d.stat().st_mtime),
    }


def read_proposals(st: Path) -> list[dict]:
    root = st / "proposals"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.glob("*")):
        if d.is_dir() and not d.name.startswith("."):
            out.append(_parse_proposal(d, "current"))
    rejected = root / ".rejected"
    if rejected.is_dir():
        for d in sorted(rejected.glob("*"), reverse=True):
            if d.is_dir():
                out.append(_parse_proposal(d, "rejected"))
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
        body = _read(d / "SKILL.md")
        fm = _garden.parse_frontmatter(body)
        hist = d / ".history"
        versions = len(list(hist.glob("*.md"))) if hist.is_dir() else 0
        out.append({"id": d.name, "name": fm.get("name", d.name),
                    "description": fm.get("description", ""),
                    "version": _garden.get_version(body) or 1,
                    "revisions": versions,
                    "body": body,
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


# ------------------------------------------------------------------ producers
# The LLM-backed commands that advance the garden (`garden maintain | propose |
# evolve`, `garden tool mine | catalog`). Same in-process reuse as the gates so
# the UI drives the exact CLI code paths. These call an LLM and can run for a
# while; a single lock serialises them because they all read/write one store.

_PRODUCER_LOCK = threading.Lock()


def _backend_model(body: dict) -> tuple[str, str | None]:
    """Resolve backend/model: request body wins, else the store config, else the
    same `claude` default the CLI uses."""
    cfg = _garden.read_config()
    backend = body.get("backend") or cfg.get("backend") or "claude"
    model = body.get("model") or cfg.get("model") or None
    return backend, model


def _run_producer(fn, *args) -> dict:
    """Run a producer, capturing BOTH stdout and stderr (producers narrate via
    `log()` -> stderr and print result JSON to stdout) so the UI shows the full
    run. `die()` raises SystemExit; we surface it rather than kill the server."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            result = fn(*args)
    except SystemExit as e:
        return {"ok": False, "error": str(e) or "command failed",
                "log": (err.getvalue() + out.getvalue()).strip()}
    except Exception as e:  # keep the server alive; surface the failure
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "log": (err.getvalue() + out.getvalue()).strip()}
    res = {"ok": True, "log": (err.getvalue() + out.getvalue()).strip()}
    if isinstance(result, dict):
        res["result"] = result
    return res


def run_command(command: str, body: dict) -> dict:
    """Dispatch a producer command by name. Serialised by _PRODUCER_LOCK; a
    concurrent request returns busy rather than racing on the store."""
    dry = bool(body.get("dry_run", False))
    backend, model = _backend_model(body)

    def _maintain():
        return _skills.maintain(dry, None, backend, model)

    def _propose():
        return _skills.propose(dry, None, backend, model)

    def _evolve():
        _skills.maintain(dry, None, backend, model)
        return _skills.propose(dry, None, backend, model)

    def _tool_mine():
        return _tools.mine(dry, backend, model)

    def _tool_catalog():
        return _tools.catalog()

    table = {
        "maintain": _maintain,
        "propose": _propose,
        "evolve": _evolve,
        "tool-mine": _tool_mine,
        "tool-catalog": _tool_catalog,
    }
    fn = table.get(command)
    if not fn:
        return {"ok": False, "error": f"unknown command: {command}"}
    if not _PRODUCER_LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True,
                "error": "another garden command is already running"}
    try:
        return _run_producer(fn)
    finally:
        _PRODUCER_LOCK.release()


# ---------------------------------------------------------- streaming producers
# The buffered path above runs producers in-process and returns one blob. The
# streaming path below spawns the real `garden` CLI under a pty and pumps its
# output to the browser over SSE, so the tend panel shows a producer narrate
# live. A pty (not a plain pipe) is what makes the child line-buffer its stderr
# — otherwise Python block-buffers and nothing would appear until it exits.
#
# NB: this streams the producer's own narration (its `log()` calls). The inner
# `claude -p` invocation (`_garden.call_llm`) still runs capture_output=True, so
# the model's own output stays a black box until that call returns — the multi-
# second pauses you see are that call. Token-level streaming would be a separate
# change to `_garden._claude_cli` (Popen + incremental reads).

# The garden CLI re-invoked as a subprocess (uv shebang resolves its deps).
GARDEN = HERE / "garden"

_STREAM_ARGS = {
    "maintain": ["maintain"],
    "propose": ["propose"],
    "evolve": ["evolve"],
    "tool-mine": ["tool", "mine"],
    "tool-catalog": ["tool", "catalog"],
}

# CSI / OSC / two-char escapes — strip so the panel shows clean text.
_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")

_active_lock = threading.Lock()
_active_proc: subprocess.Popen | None = None


def _strip_ansi(s: str) -> str:
    # Drop escape sequences, then normalise pty newlines (CRLF / lone CR -> LF)
    # so the panel's <pre> renders clean lines.
    return _ANSI.sub("", s).replace("\r\n", "\n").replace("\r", "\n")


def _run_argv(command: str, opts: dict) -> list[str] | None:
    """Map a UI command name to the `garden` argv, threading through the same
    --dry-run / --backend / --model options the buffered path honours."""
    base = _STREAM_ARGS.get(command)
    if base is None:
        return None
    argv = [str(GARDEN), *base]
    if opts.get("dry_run"):
        argv.append("--dry-run")
    if command != "tool-catalog":  # catalog takes no backend/model
        if opts.get("backend"):
            argv += ["--backend", opts["backend"]]
        if opts.get("model"):
            argv += ["--model", opts["model"]]
    return argv


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM the child's whole process group (start_new_session gave it one)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _pty_stream(argv: list[str], emit) -> int:
    """Run argv under a pty, calling emit('log', {'chunk': ...}) as output
    arrives. If emit raises (client disconnected), the child is killed and the
    exception propagates. Returns the process exit code."""
    global _active_proc
    master, slave = pty.openpty()
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color",
           "WIKIGARDEN_STREAM": "1"}  # echo claude's token stream into the pty
    proc = subprocess.Popen(
        argv, stdin=slave, stdout=slave, stderr=slave,
        start_new_session=True, env=env, close_fds=True,
    )
    os.close(slave)
    with _active_lock:
        _active_proc = proc
    try:
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:       # EIO on macOS when the child closes the pty
                break
            if not data:          # EOF on Linux
                break
            emit("log", {"chunk": _strip_ansi(data.decode("utf-8", "replace"))})
    except BaseException:
        _terminate(proc)          # client vanished — take the child down with us
        raise
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        proc.wait()
        with _active_lock:
            _active_proc = None
    return proc.returncode


def cancel_active() -> dict:
    """Kill the currently streaming producer, if any."""
    with _active_lock:
        proc = _active_proc
    if proc is None:
        return {"ok": False, "error": "nothing running"}
    _terminate(proc)
    return {"ok": True}


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

    def _sse(self, event: str, data: dict) -> None:
        """Write one Server-Sent Event and flush. Raises if the client is gone."""
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
        self.wfile.write(payload)
        self.wfile.flush()

    def _stream_run(self, command: str, query: dict) -> None:
        """SSE endpoint: spawn `garden <command>` under a pty and stream its
        output live. Serialised with the buffered path via _PRODUCER_LOCK."""
        opts = {
            "dry_run": (query.get("dry_run", [""])[0] in ("1", "true", "yes")),
            "backend": (query.get("backend", [""])[0] or None),
            "model": (query.get("model", [""])[0] or None),
        }
        argv = _run_argv(command, opts)
        if argv is None:
            return self._send_json({"error": f"unknown command: {command}"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        if not _PRODUCER_LOCK.acquire(blocking=False):
            try:
                self._sse("busy", {"error": "another garden command is already running"})
                self._sse("done", {"code": -1, "busy": True})
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            return
        try:
            self._sse("start", {"command": command})
            code = _pty_stream(argv, self._sse)
            self._sse("done", {"code": code})
        except (BrokenPipeError, ConnectionError, OSError):
            pass  # client disconnected; _pty_stream already killed the child
        finally:
            _PRODUCER_LOCK.release()

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
        parts = [p for p in path.split("/") if p]  # ['api','run','<cmd>','stream']
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "run" and parts[3] == "stream":
            return self._stream_run(parts[2], parse_qs(parsed.query))
        if path.startswith("/api/"):
            return self._send_json({"error": "not found"}, 404)
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/pick-project":
            body = self._read_body()
            return self._send_json(pick_folder(body.get("start", "")))
        if path == "/api/run/cancel":
            return self._send_json(cancel_active())
        parts = [p for p in path.split("/") if p]  # ['api','proposals','<name>','accept']
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "run":
            res = run_command(parts[2], self._read_body())
            status = 200 if res.get("ok") else (409 if res.get("busy") else 400)
            return self._send_json(res, status)
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


def _bind(host: str, port: int, tries: int = 20) -> ThreadingHTTPServer:
    """Bind the requested port, falling forward to the next free one if it's busy.

    Port 0 means "any free port" and is honoured as-is. After `tries` busy ports
    in a row we let the OS pick, so tend still comes up on a crowded machine.
    """
    if port == 0:
        return ThreadingHTTPServer((host, 0), Handler)
    for candidate in range(port, port + tries):
        try:
            return ThreadingHTTPServer((host, candidate), Handler)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            print(f"[wiki-garden] port {candidate} busy, trying {candidate + 1}")
    return ThreadingHTTPServer((host, 0), Handler)


def serve(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    """Boot the tend server. Blocks until Ctrl-C."""
    st = _garden.store_root()
    _garden.ensure_skeleton(st)
    httpd = _bind(host, port)
    port = httpd.server_address[1]
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
