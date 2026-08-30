"""Tools layer for the `garden` CLI: capture, gate, mine.

Imported by the `garden` Typer app. Functions do the work, log, print their JSON
result, and return the result dict.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from datetime import date, datetime
from pathlib import Path

import _garden
from _garden import call_llm, die, log, parse_json, prompt, store_root, tool_settings

META = {"TOOL.md", "PURPOSE.md", "proposal.json"}


# ---------------------------------------------------------------- capture

def _tool_md(prop: dict, full: str) -> str:
    args_lines = "\n".join(
        f"  - {a.get('name','')}: {a.get('desc','')}"
        f"{' (required)' if a.get('required') else ''}"
        f"{(' [default: ' + str(a['default']) + ']') if a.get('default') else ''}"
        for a in prop.get("args", [])) or "  (none)"
    return (f"---\nname: {full}\ndescription: {prop.get('description','').strip()}\n"
            f"runtime: {prop.get('runtime','')}\nusage: {prop.get('usage','').strip()}\n"
            f"deps: [{', '.join(prop.get('deps', []))}]\n---\n"
            f"# {full}\n\n{prop.get('description','').strip()}\n\n"
            f"## Usage\n```\n{prop.get('usage','').strip()}\n```\n\n"
            f"## Args\n{args_lines}\n\n"
            f"## Requires\n{', '.join(prop.get('deps', [])) or 'none'}\n\n"
            f"## Safety\n{prop.get('safety_notes','').strip() or 'No notable side effects.'}\n")


def _tool_purpose_md(prop: dict, source_note: str) -> str:
    return (f"pattern: {prop.get('pattern','') or '(manual capture)'}\n"
            f"proposed: {date.today().isoformat()}\n"
            f"gate: human=pending review=pending\n"
            f"source: {source_note}\n"
            f"rationale: {prop.get('report','').strip()}\n")


def _stage_tool(store: Path, prop: dict, prefix: str, source_note: str, dry_run: bool) -> str | None:
    if prop.get("decision") != "tool":
        return None
    full = f"{prefix}{prop.get('name') or 'unnamed'}"
    pdir = store / "tool-proposals" / f"{datetime.now().strftime('%Y-%m-%dT%H-%M')}_{prop.get('name') or 'unnamed'}"
    if dry_run:
        return str(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    exe = pdir / full
    exe.write_text(prop["script"].rstrip() + "\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (pdir / "TOOL.md").write_text(_tool_md(prop, full))
    (pdir / "PURPOSE.md").write_text(_tool_purpose_md(prop, source_note))
    (pdir / "proposal.json").write_text(json.dumps(prop, indent=2))
    return str(pdir)


def capture(from_: str | None, name: str | None, runtime: str | None, dry_run: bool,
            plan_file: str | None, backend: str, model: str | None,
            source_text: str | None = None) -> dict:
    store = store_root()
    prefix, default_runtime = tool_settings()
    runtime = runtime or default_runtime
    log(f"store: {store}  prefix: {prefix}  runtime: {runtime}")

    source_note = from_ or ("inline" if source_text is not None else "stdin")
    if plan_file:
        prop = json.loads(Path(plan_file).read_text())
    else:
        if source_text is not None:
            raw = source_text
        elif from_:
            raw = Path(from_).read_text()
        elif not sys.stdin.isatty() and (data := sys.stdin.read()).strip():
            raw = data
        else:
            die("no source script: pass --from <path> or pipe the script on stdin")
        system = prompt("tool-generalizer")
        guidance = []
        if (inline := _garden.config_get("tool_guidance")):
            guidance.append(inline)
        if (overlay := _garden.prompt_overlays(["tool", f"tool.{runtime}"])):
            guidance.append(overlay)
        if guidance:
            system += ("\n\n## User conventions (house style — follow these for "
                       "structure/runtime/style; the safety rules above still override):\n"
                       + "\n\n".join(guidance))
            log(f"applied user tool guidance ({len(guidance)} source(s))")
        user = (f"TARGET RUNTIME: {runtime}\nSUGGESTED NAME: {name or '(you choose)'}\n\n"
                f"RAW SCRIPT:\n{raw}\n\nReturn the JSON.")
        try:
            prop = parse_json(call_llm(system, user, backend, model))
        except RuntimeError as e:
            die(str(e))
        prop.setdefault("runtime", runtime)

    staged = _stage_tool(store, prop, prefix, source_note, dry_run)
    out = {"dry_run": dry_run, "decision": prop.get("decision"),
           "tool": (prefix + prop["name"]) if prop.get("name") else None,
           "runtime": prop.get("runtime"), "staged_at": staged, "report": prop.get("report", "")}
    print(json.dumps(out, indent=2))
    if prop.get("decision") == "tool" and dry_run:
        print("\n--- generated script (preview) ---")
        print(prop.get("script", "").rstrip())
    if prop.get("decision") == "tool" and not dry_run:
        log(f"staged tool at {staged} — review the code & gate before installing")
    return out


# ---------------------------------------------------------------- tool gate

def _tp_dir(st: Path, name: str) -> Path:
    props = st / "tool-proposals"
    if (props / name).is_dir():
        return props / name
    hits = [d for d in props.glob("*") if d.is_dir() and not d.name.startswith(".") and d.name.endswith(f"_{name}")]
    if len(hits) == 1:
        return hits[0]
    die(f"'{name}' {'is ambiguous: ' + ', '.join(d.name for d in hits) if hits else 'not found (try: garden tool gate list)'}")


def _exe_of(pdir: Path) -> Path:
    exes = [f for f in pdir.iterdir() if f.is_file() and f.name not in META]
    if not exes:
        die(f"no executable found in {pdir.name}")
    return exes[0]


def _tp_load(pdir: Path) -> dict:
    return json.loads((pdir / "proposal.json").read_text())


def _run_review(st: Path, pdir: Path, backend: str, model: str | None) -> dict:
    exe = _exe_of(pdir)
    manifest = (pdir / "TOOL.md").read_text() if (pdir / "TOOL.md").exists() else ""
    user = (f"TOOL MANIFEST (TOOL.md):\n{manifest}\n\n"
            f"TOOL SOURCE ({exe.name}):\n{exe.read_text()}\n\nReturn the JSON review.")
    try:
        out = parse_json(call_llm(prompt("tool-review"), user, backend, model))
    except SystemExit:
        raise
    except Exception as e:
        return {"verdict": "skipped", "findings": [], "summary": f"review error: {e}"}
    resdir = st / "eval" / "results"; resdir.mkdir(parents=True, exist_ok=True)
    (resdir / f"{datetime.now().strftime('%Y-%m-%dT%H-%M')}_{pdir.name}_toolreview.json").write_text(json.dumps(out, indent=2))
    return out


def _tool_record(st: Path, prop: dict, human: str, review: str, decision: str, note: str, scope: str = "global"):
    rec = {"date": date.today().isoformat(), "tool": prop.get("name", ""),
           "runtime": prop.get("runtime", ""), "human": human, "review": review,
           "decision": decision, "scope": scope, "note": note}
    ledger = st / "wiki" / "tool-impact.jsonl"; ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _tool_set_gate(pdir: Path, human: str, review: str):
    pf = pdir / "PURPOSE.md"
    if not pf.exists():
        return
    lines = [f"gate: human={human} review={review}" if ln.startswith("gate:") else ln
             for ln in pf.read_text().splitlines()]
    pf.write_text("\n".join(lines) + "\n")


def tool_gate_list() -> dict:
    st = store_root(); log(f"store: {st}")
    props = [d for d in sorted((st / "tool-proposals").glob("*")) if d.is_dir() and not d.name.startswith(".")]
    if not props:
        print("(no staged tools)")
        return {"tools": []}
    for d in props:
        prop = _tp_load(d)
        print(f"- {d.name}\n    tool: {_exe_of(d).name}  runtime: {prop.get('runtime')}")
        print(f"    {prop.get('description','').strip()[:100]}")
    return {"tools": [d.name for d in props]}


def tool_gate_show(name: str):
    st = store_root(); pdir = _tp_dir(st, name); exe = _exe_of(pdir)
    print(f"=== {pdir.name} ===\n")
    print("--- PURPOSE.md ---"); print((pdir / "PURPOSE.md").read_text())
    print("--- TOOL.md ---"); print((pdir / "TOOL.md").read_text())
    print(f"--- SOURCE: {exe.name} (READ THIS before accepting) ---")
    print(exe.read_text())


def tool_gate_review(name: str, backend: str, model: str | None):
    st = store_root(); log(f"store: {st}")
    print(json.dumps(_run_review(st, _tp_dir(st, name), backend, model), indent=2))


def tool_gate_accept(name: str, note: str, no_install: bool, scope: str,
                     project_dir: str | None, backend: str, model: str | None) -> dict:
    st = store_root(); log(f"store: {st}")
    pdir = _tp_dir(st, name); prop = _tp_load(pdir)
    tname = prop.get("name") or pdir.name.split("_", 1)[-1]
    exe = _exe_of(pdir)
    review = _run_review(st, pdir, backend, model)
    verdict = review.get("verdict", "skipped")
    if verdict == "unsafe":
        log(f"static review flagged UNSAFE: {review.get('summary','')} — accepting on human override")
    if scope == "project":
        proj = _garden.resolve_project_dir(project_dir)
        dest = proj / ".claude" / "wiki-garden-tools" / tname
    else:
        dest = st / "tools" / tname
    if dest.exists():
        die(f"{dest} already exists — reject or edit instead")
    _tool_set_gate(pdir, "accepted", verdict)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdir), str(dest))
    _tool_record(st, prop, "accepted", verdict, "accepted", note or "", scope)
    installed = None
    dest_exe = dest / exe.name
    if not no_install:
        if scope == "project":
            binp = proj / "bin" / exe.name; binp.parent.mkdir(parents=True, exist_ok=True)
            if not binp.exists():
                shutil.copy2(dest_exe, binp); installed = str(binp)
            cat = _garden.write_project_tools_catalog(proj)
        else:
            link = Path.home() / ".local" / "bin" / exe.name; link.parent.mkdir(parents=True, exist_ok=True)
            if not link.exists():
                os.symlink(dest_exe, link); installed = str(link)
            cat = _garden.write_tools_catalog(st)
    else:
        cat = _garden.write_tools_catalog(st) if scope == "global" else {"count": 0}
    if scope == "global":
        _garden.git_commit(st, f"tool gate: accept {tname}")
    out = {"decision": "accepted", "tool": exe.name, "review": verdict, "scope": scope,
           "activated_at": str(dest), "installed_at": installed, "catalog_tools": cat["count"]}
    print(json.dumps(out, indent=2))
    log(f"accepted {exe.name} ({scope}): {dest}" + (f"; installed -> {installed}" if installed else ""))
    return out


def tool_gate_reject(name: str, note: str, review: bool, backend: str, model: str | None) -> dict:
    st = store_root(); log(f"store: {st}")
    if not note:
        die("reject requires --note (why — recorded in tool-impact.jsonl)")
    pdir = _tp_dir(st, name); prop = _tp_load(pdir)
    r = _run_review(st, pdir, backend, model) if review else {"verdict": "not-run"}
    _tool_record(st, prop, "rejected", r.get("verdict", "not-run"), "rejected", note)
    arch = st / "tool-proposals" / ".rejected"; arch.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdir), str(arch / pdir.name))
    _garden.git_commit(st, f"tool gate: reject {prop.get('name', name)}")
    out = {"decision": "rejected", "tool": prop.get("name"), "note": note, "archived": str(arch / pdir.name)}
    print(json.dumps(out, indent=2))
    log(f"rejected {prop.get('name')} — recorded in tool-impact.jsonl")
    return out


def catalog() -> dict:
    st = store_root(); out = _garden.write_tools_catalog(st)
    log(f"store: {st}")
    print(json.dumps(out, indent=2))
    return out


# ---------------------------------------------------------------- mine

def _unmined_traces(store: Path) -> list[str]:
    raw = store / "raw"; cur = store / "tools" / ".mined.log"
    done = set(cur.read_text().split()) if cur.exists() else set()
    return sorted(f.name for f in raw.glob("*.md") if f.name not in done) if raw.exists() else []


def _known_names(store: Path) -> set[str]:
    names = set()
    for sub in ("tools", "tool-proposals"):
        d = store / sub
        if d.exists():
            for p in d.glob("*"):
                if p.is_dir() and not p.name.startswith("."):
                    names.add(p.name.split("_", 1)[-1] if sub == "tool-proposals" else p.name)
    ledger = store / "wiki" / "tool-impact.jsonl"
    if ledger.exists():
        for ln in ledger.read_text().splitlines():
            try:
                r = json.loads(ln)
                if r.get("decision") == "rejected":
                    names.add(r.get("tool", ""))
            except json.JSONDecodeError:
                pass
    return {n for n in names if n}


def mine(dry_run: bool, backend: str, model: str | None) -> dict:
    store = store_root(); log(f"store: {store}")
    traces = _unmined_traces(store)
    if not traces:
        log("no new traces to mine")
        return {"mined_traces": 0, "staged": []}
    log(f"mining {len(traces)} trace(s): {', '.join(traces)}")
    existing = _known_names(store)
    blob = "\n\n".join(f"### TRACE: {t}\n{(store/'raw'/t).read_text()}" for t in traces)
    user = (f"EXISTING TOOLS: {', '.join(sorted(existing)) or '(none)'}\n"
            f"REJECTED TOOLS: (merged into EXISTING)\n\nRECENT TRACES:\n{blob}\n\nReturn the JSON.")
    try:
        result = parse_json(call_llm(prompt("tool-miner"), user, backend, model))
    except RuntimeError as e:
        die(str(e))
    candidates = [c for c in result.get("candidates", []) if c.get("name") not in existing]
    staged = []
    for c in candidates:
        name, example = c.get("name"), c.get("example_command", "")
        if not name or not example.strip():
            continue
        if dry_run:
            staged.append({"name": name, "would_stage": True, "why": c.get("why", "")})
            continue
        try:
            r = capture(None, name, c.get("runtime_hint"), False, None, backend, model, source_text=example)
            staged.append({"name": name, "staged": bool(r.get("staged_at")), "at": r.get("staged_at")})
        except SystemExit:
            staged.append({"name": name, "staged": False})
    if not dry_run:
        cur = store / "tools" / ".mined.log"; cur.parent.mkdir(parents=True, exist_ok=True)
        with cur.open("a") as fh:
            for t in traces:
                fh.write(t + "\n")
    out = {"dry_run": dry_run, "mined_traces": len(traces),
           "candidates": len(result.get("candidates", [])), "new": len(candidates),
           "staged": staged, "report": result.get("report", "")}
    print(json.dumps(out, indent=2))
    if staged and not dry_run:
        log("staged mined candidates — review with garden tool gate")
    return out
