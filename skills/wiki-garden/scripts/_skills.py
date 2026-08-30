"""Skills+wiki pipeline for the `garden` CLI: maintain, propose, gate.

Imported by the `garden` Typer app. Each function does the work, logs, prints its
JSON result, and returns the result dict.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path

import _garden
from _garden import call_llm, die, log, parse_json, prompt, store_root


# ---------------------------------------------------------------- maintain

def _unprocessed_traces(store: Path) -> list[str]:
    raw = store / "raw"
    processed = store / "wiki" / ".processed.log"
    done = {ln.strip() for ln in processed.read_text().splitlines() if ln.strip()} if processed.exists() else set()
    return sorted(f.name for f in raw.glob("*.md") if f.name not in done) if raw.exists() else []


def _patterns_context(store: Path) -> str:
    pdir = store / "wiki" / "patterns"
    files = sorted(pdir.glob("*.md")) if pdir.exists() else []
    if not files:
        return "(no existing patterns yet)"
    return "\n\n".join(f"### FILE: {f.name}\n{f.read_text()}" for f in files)


def _pattern_path(store: Path, pid: str) -> Path:
    return store / "wiki" / "patterns" / f"{pid}.md"


def _section_body(text: str, section: str) -> str:
    m = re.search(rf"^##\s+{re.escape(section)}\s*\n(.*?)(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else ""


def _replace_section(body: str, section: str, content: str) -> str:
    pat = re.compile(rf"(^##\s+{re.escape(section)}\s*\n)(.*?)(?=^##\s|\Z)", re.DOTALL | re.MULTILINE)
    if not pat.search(body):
        return body.rstrip() + f"\n## {section}\n{content.rstrip()}\n"
    return pat.sub(lambda m: m.group(1) + content.rstrip() + "\n", body)


def _add_trace_ref(fm: str, ref: str) -> str:
    m = re.search(r"^trace_refs:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if not m:
        return fm
    items = [x.strip() for x in m.group(1).split(",") if x.strip()]
    if ref not in items:
        items.append(ref)
    return fm[:m.start()] + f"trace_refs: [{', '.join(items)}]" + fm[m.end():]


def _apply_plan(store: Path, plan: dict, dry_run: bool) -> list[str]:
    changes: list[str] = []
    for op in plan.get("ops", []):
        kind, pid = op.get("op"), op.get("id", "")
        path = _pattern_path(store, pid)
        if kind == "create_pattern":
            if path.exists():
                changes.append(f"skip create (exists): {pid}"); continue
            changes.append(f"create pattern: {pid}")
            if not dry_run:
                path.write_text(op["content"].rstrip() + "\n")
        elif kind in ("append_evidence", "replace_section", "set_status"):
            if not path.exists():
                changes.append(f"skip {kind} (missing): {pid}"); continue
            text = path.read_text()
            if kind == "append_evidence":
                text = _add_trace_ref(text, op.get("trace_ref", ""))
                text = _replace_section(text, "Evidence",
                    _section_body(text, "Evidence").rstrip() + f"\n- {op.get('trace_ref','')}: {op['bullet']}")
                changes.append(f"append evidence: {pid}")
            elif kind == "replace_section":
                text = _replace_section(text, op["section"], op["content"])
                changes.append(f"replace {op['section']}: {pid}")
            elif kind == "set_status":
                text = re.sub(r"^status:.*$", f"status: {op['status']}", text, count=1, flags=re.MULTILINE)
                changes.append(f"set status={op['status']}: {pid}")
            if not dry_run:
                path.write_text(text)
        else:
            changes.append(f"unknown op ignored: {kind}")
    return changes


def _record_iteration(store: Path, plan: dict, changes: list[str], dry_run: bool):
    processed = list(plan.get("processed", []))
    entry = (f"\n## {date.today().isoformat()} — wiki maintenance\n"
             f"- traces consumed: {', '.join(processed) or 'none'}\n"
             f"- changes: {', '.join(changes) or 'none'}\n"
             f"- report: {plan.get('report','').strip()}\n")
    if dry_run:
        return
    logf = store / "wiki" / "evolution-log.md"
    content = logf.read_text() if logf.exists() else "# Evolution Log\n\n<!-- newest first -->\n"
    marker = "<!-- newest first -->\n"
    content = content.replace(marker, marker + entry, 1) if marker in content else content + entry
    logf.write_text(content)
    with (store / "wiki" / ".processed.log").open("a") as fh:
        for name in processed:
            fh.write(name + "\n")


def maintain(dry_run: bool, plan_file: str | None, backend: str, model: str | None) -> dict:
    store = store_root()
    log(f"store: {store}")
    if plan_file:
        plan = json.loads(Path(plan_file).read_text())
    else:
        traces = _unprocessed_traces(store)
        if not traces:
            log("wiki up to date — no new traces")
            return {"changes": [], "processed": []}
        log(f"unprocessed traces: {', '.join(traces)}")
        blob = "\n\n".join(f"### TRACE FILE: {t}\n{(store/'raw'/t).read_text()}" for t in traces)
        user = (f"CURRENT WIKI PATTERNS:\n{_patterns_context(store)}\n\n"
                f"NEW UNPROCESSED TRACES:\n{blob}\n\n"
                f"Today is {date.today().isoformat()}. Return the JSON patch-plan.")
        try:
            plan = parse_json(call_llm(prompt("wiki-maintainer"), user, backend, model))
        except RuntimeError as e:
            die(str(e))
        plan.setdefault("processed", [])
        for t in traces:
            if t not in plan["processed"]:
                plan["processed"].append(t)
    changes = _apply_plan(store, plan, dry_run)
    _record_iteration(store, plan, changes, dry_run)
    out = {"dry_run": dry_run, "changes": changes,
           "processed": plan.get("processed", []), "report": plan.get("report", "")}
    print(json.dumps(out, indent=2))
    return out


# ---------------------------------------------------------------- propose

def _propose_context(store: Path) -> str:
    pdir = store / "wiki" / "patterns"
    patterns = "\n\n".join(f"### PATTERN FILE: {f.name}\n{f.read_text()}"
                           for f in sorted(pdir.glob("*.md"))) if pdir.exists() else ""
    sdir = store / "skills"
    skills = []
    if sdir.exists():
        for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
            sm = d / "SKILL.md"
            skills.append(f"- {d.name}:\n{sm.read_text()[:400] if sm.exists() else '(no SKILL.md)'}")
    ledger = store / "wiki" / "skill-impact.jsonl"
    ledger_ctx = (ledger.read_text().strip() if ledger.exists() else "") or "(no prior decisions)"
    props = store / "proposals"
    pending = []
    if props.exists():
        for d in sorted(p for p in props.iterdir() if p.is_dir() and not p.name.startswith(".")):
            pj = d / "proposal.json"
            if pj.exists():
                try:
                    pd = json.loads(pj.read_text())
                    pending.append(f"- {pd.get('skill_name', d.name)} (pattern: {pd.get('pattern', '?')})")
                except (json.JSONDecodeError, OSError):
                    pending.append(f"- {d.name}")
            else:
                pending.append(f"- {d.name}")
    return (f"CURRENT WIKI PATTERNS:\n{patterns or '(no patterns yet)'}\n\n"
            f"EXISTING SKILLS:\n{chr(10).join(skills) or '(no skills yet)'}\n\n"
            f"PENDING PROPOSALS (un-gated — do NOT restage a duplicate for the same "
            f"skill_name/pattern; return no_change or edit an activated skill instead):\n"
            f"{chr(10).join(pending) or '(none pending)'}\n\n"
            f"SKILL-IMPACT LEDGER (past decisions — do not re-propose rejected):\n{ledger_ctx}")


def _skill_purpose_md(prop: dict) -> str:
    return (f"pattern: {prop.get('pattern','')}\n"
            f"proposed: {date.today().isoformat()}\n"
            f"gate: human=pending retro=pending\n"
            f"rationale: {prop.get('rationale','').strip()}\n")


def propose(dry_run: bool, plan_file: str | None, backend: str, model: str | None) -> dict:
    store = store_root()
    log(f"store: {store}")
    if plan_file:
        prop = json.loads(Path(plan_file).read_text())
    else:
        user = _propose_context(store) + f"\n\nToday is {date.today().isoformat()}. Return the JSON proposal."
        try:
            prop = parse_json(call_llm(prompt("skill-proposer"), user, backend, model))
        except RuntimeError as e:
            die(str(e))
    staged = None
    if prop.get("decision") == "propose":
        name = prop.get("skill_name") or "unnamed"
        pdir = store / "proposals" / f"{datetime.now().strftime('%Y-%m-%dT%H-%M')}_{name}"
        if not dry_run:
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / "SKILL.md").write_text(prop["skill_md"].rstrip() + "\n")
            (pdir / "PURPOSE.md").write_text(_skill_purpose_md(prop))
            (pdir / "proposal.json").write_text(json.dumps(prop, indent=2))
        staged = str(pdir)
    out = {"dry_run": dry_run, "decision": prop.get("decision"),
           "skill_name": prop.get("skill_name"), "pattern": prop.get("pattern"),
           "staged_at": staged, "report": prop.get("report", "")}
    print(json.dumps(out, indent=2))
    if prop.get("decision") == "propose" and not dry_run:
        log(f"staged proposal at {staged} — review & gate before activating")
    return out


# ---------------------------------------------------------------- gate

def _proposal_dir(st: Path, name: str) -> Path:
    props = st / "proposals"
    if (props / name).is_dir():
        return props / name
    hits = [d for d in props.glob("*") if d.is_dir() and not d.name.startswith(".") and d.name.endswith(f"_{name}")]
    if len(hits) == 1:
        return hits[0]
    die(f"'{name}' {'is ambiguous: ' + ', '.join(d.name for d in hits) if hits else 'not found (try: garden gate list)'}")


def _load(pdir: Path) -> dict:
    return json.loads((pdir / "proposal.json").read_text())


def _run_retro(st: Path, pdir: Path, backend: str, model: str | None) -> dict:
    skill_md = (pdir / "SKILL.md").read_text()
    stash = sorted((st / "eval" / "stash").glob("*.md")) if (st / "eval" / "stash").exists() else []
    if not stash:
        return {"result": "skipped", "reason": "eval/stash is empty", "cases": []}
    cases = []
    for task in stash:
        user = f"PAST TASK:\n{task.read_text()}\n\nCANDIDATE SKILL (SKILL.md):\n{skill_md}\n\nReturn the JSON verdict."
        try:
            v = parse_json(call_llm(prompt("retro-eval"), user, backend, model))
        except SystemExit:
            raise
        except Exception as e:
            v = {"verdict": "neutral", "applies": False, "why": f"eval error: {e}"}
        v["task"] = task.name
        cases.append(v)
    harmful = [c for c in cases if c.get("verdict") == "harmful"]
    out = {"result": "fail" if harmful else "pass", "harmful": len(harmful), "cases": cases}
    resdir = st / "eval" / "results"; resdir.mkdir(parents=True, exist_ok=True)
    (resdir / f"{datetime.now().strftime('%Y-%m-%dT%H-%M')}_{pdir.name}.json").write_text(json.dumps(out, indent=2))
    return out


def _record(st: Path, prop: dict, human: str, retro: str, decision: str, note: str, scope: str = "global"):
    rec = {"date": date.today().isoformat(), "proposal": prop.get("skill_name", ""),
           "pattern": prop.get("pattern", ""), "human": human, "retro": retro,
           "decision": decision, "scope": scope, "note": note}
    ledger = st / "wiki" / "skill-impact.jsonl"; ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _set_gate(pdir: Path, human: str, retro: str):
    pf = pdir / "PURPOSE.md"
    if not pf.exists():
        return
    lines = [f"gate: human={human} retro={retro}" if ln.startswith("gate:") else ln
             for ln in pf.read_text().splitlines()]
    pf.write_text("\n".join(lines) + "\n")


def gate_list() -> dict:
    st = store_root(); log(f"store: {st}")
    props = [p for p in sorted((st / "proposals").glob("*")) if p.is_dir() and not p.name.startswith(".")]
    if not props:
        print("(no staged proposals)")
        return {"proposals": []}
    for d in props:
        prop = _load(d)
        print(f"- {d.name}\n    skill: {prop.get('skill_name')}  pattern: {prop.get('pattern')}")
        print(f"    rationale: {prop.get('rationale','').strip()}")
    return {"proposals": [d.name for d in props]}


def gate_show(name: str):
    st = store_root(); pdir = _proposal_dir(st, name)
    print(f"=== {pdir.name} ===\n")
    print("--- PURPOSE.md ---"); print((pdir / "PURPOSE.md").read_text())
    print("--- SKILL.md ---"); print((pdir / "SKILL.md").read_text())


def gate_retro(name: str, backend: str, model: str | None):
    st = store_root(); log(f"store: {st}")
    print(json.dumps(_run_retro(st, _proposal_dir(st, name), backend, model), indent=2))


def gate_accept(name: str, note: str, no_install: bool, scope: str,
                project_dir: str | None, backend: str, model: str | None) -> dict:
    st = store_root(); log(f"store: {st}")
    pdir = _proposal_dir(st, name); prop = _load(pdir)
    sk_name = prop.get("skill_name") or pdir.name.split("_", 1)[-1]
    retro = _run_retro(st, pdir, backend, model)
    retro_str = {"pass": "passed", "fail": "failed", "skipped": "skipped"}.get(retro["result"], retro["result"])
    if retro["result"] == "fail":
        log(f"retro-eval FAILED ({retro['harmful']} harmful) — accepting on human override")
    if scope == "project":
        dest = _garden.resolve_project_dir(project_dir) / ".claude" / "skills" / sk_name
    else:
        dest = st / "skills" / sk_name
    is_edit = prop.get("kind") == "edit_skill"
    _set_gate(pdir, "accepted", retro_str)
    new_md = (pdir / "SKILL.md").read_text()
    if dest.exists():
        if not is_edit:
            die(f"{dest} already exists — reject, or propose an edit_skill instead")
        # Edit: archive the current version, bump, overwrite in place.
        old_md = (dest / "SKILL.md").read_text()
        version = (_garden.get_version(old_md) or 1) + 1
        hist = dest / ".history"; hist.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        (hist / f"v{version - 1}_{stamp}.md").write_text(old_md)
        (dest / "SKILL.md").write_text(_garden.set_version(new_md, version))
        (dest / "PURPOSE.md").write_text((pdir / "PURPOSE.md").read_text())
        (dest / "proposal.json").write_text((pdir / "proposal.json").read_text())
        accepted_arch = st / "proposals" / ".accepted"; accepted_arch.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdir), str(accepted_arch / pdir.name))
    else:
        # New skill: stamp version 1 (if unset) and move the proposal into place.
        version = _garden.get_version(new_md) or 1
        (pdir / "SKILL.md").write_text(_garden.set_version(new_md, version))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdir), str(dest))
    _record(st, prop, "accepted", retro_str, "accepted", note or "", scope)
    installed = None
    if scope == "global" and not no_install:
        link = Path.home() / ".claude" / "skills" / sk_name
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            os.symlink(dest, link); installed = str(link)
    elif scope == "project":
        installed = str(dest)
    if scope == "global":
        _garden.git_commit(st, f"gate: accept {sk_name} v{version}"
                               + (" (edit)" if is_edit else ""))
    out = {"decision": "accepted", "skill": sk_name, "version": version, "edit": is_edit,
           "retro": retro_str, "scope": scope, "activated_at": str(dest), "installed_at": installed}
    print(json.dumps(out, indent=2))
    log(f"accepted {sk_name} v{version} ({scope}): {dest}")
    return out


def gate_reject(name: str, note: str, retro: bool, backend: str, model: str | None) -> dict:
    st = store_root(); log(f"store: {st}")
    if not note:
        die("reject requires --note (why — recorded so it is not re-proposed)")
    pdir = _proposal_dir(st, name); prop = _load(pdir)
    r = _run_retro(st, pdir, backend, model) if retro else {"result": "not-run"}
    _record(st, prop, "rejected", r["result"], "rejected", note)
    arch = st / "proposals" / ".rejected"; arch.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdir), str(arch / pdir.name))
    _garden.git_commit(st, f"gate: reject {prop.get('skill_name', name)}")
    out = {"decision": "rejected", "skill": prop.get("skill_name"), "note": note,
           "archived": str(arch / pdir.name)}
    print(json.dumps(out, indent=2))
    log(f"rejected {prop.get('skill_name')} — recorded in skill-impact.jsonl")
    return out
