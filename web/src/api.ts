// Typed client for the `garden tend` JSON API (skills/wiki-garden/scripts/_web.py).

export interface Gate {
  human?: string;
  retro?: string;
  review?: string;
}

export interface Proposal {
  id: string;
  skill_name: string;
  pattern: string;
  rationale: string;
  report: string;
  skill_md: string;
  purpose: string;
  gate: Gate;
  staged_at: string;
}

export interface Tool {
  id: string;
  name: string;
  runtime: string;
  description: string;
  tool_md: string;
  purpose: string;
  gate: Gate;
  exe_name: string | null;
  source: string;
  staged_at: string;
}

export interface Pattern {
  id: string;
  title: string;
  body: string;
  updated_at: string;
}

export interface Trace {
  id: string;
  body: string;
  captured_at: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  activated_at: string;
}

export interface LedgerRow {
  date?: string;
  decision?: string;
  note?: string;
  [k: string]: unknown;
}

export interface Snapshot {
  store: string;
  generated_at: string;
  counts: Record<string, number>;
  proposals: Proposal[];
  tools: Tool[];
  patterns: Pattern[];
  traces: Trace[];
  skills: Skill[];
  evolution: string;
  ledger: { skills: LedgerRow[]; tools: LedgerRow[] };
}

export interface GateResult {
  ok: boolean;
  log?: string;
  error?: string;
  result?: Record<string, unknown>;
}

export async function getSnapshot(): Promise<Snapshot> {
  const r = await fetch("/api/snapshot");
  if (!r.ok) throw new Error(`snapshot failed: ${r.status}`);
  return r.json();
}

type Kind = "proposals" | "tools";
type Action = "accept" | "reject";

export interface ProjectCheck {
  ok: boolean;
  reason: string;
  path?: string;
  git?: boolean;
}

export async function validateProject(path: string): Promise<ProjectCheck> {
  const r = await fetch(`/api/validate-project?path=${encodeURIComponent(path)}`);
  return r.json();
}

export interface PickResult {
  ok: boolean;
  path?: string;
  canceled?: boolean;
  reason?: string;
}

/** Pop a native OS folder dialog on the machine running the server. */
export async function pickProject(start = ""): Promise<PickResult> {
  const r = await fetch("/api/pick-project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start }),
  });
  return r.json();
}

export async function gate(
  kind: Kind,
  id: string,
  action: Action,
  body: Record<string, unknown>,
): Promise<GateResult> {
  const r = await fetch(`/api/${kind}/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}
