// Typed client for the `garden tend` JSON API (skills/wiki-garden/wiki_garden/_web.py).

export interface Gate {
  human?: string;
  retro?: string;
  review?: string;
}

export interface Proposal {
  id: string;
  status: "current" | "rejected";
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
  version: number;
  revisions: number;
  body: string;
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
  busy?: boolean;
  result?: Record<string, unknown>;
}

/** LLM-backed producer commands the UI can trigger (`garden <command>`). */
export type RunCommand = "maintain" | "propose" | "evolve" | "tool-mine" | "tool-catalog";

export type RunState = "running" | "done" | "error" | "busy";

/** One tracked execution, shown as a collapsible entry in the run panel. */
export interface RunEntry {
  id: number;
  cmd: RunCommand;
  log: string;
  status: RunState;
  code: number;
  startedAt: number; // epoch ms
  expanded: boolean;
}

/** Run a producer command server-side, returning its captured log (buffered). */
export async function runCommand(
  command: RunCommand,
  body: Record<string, unknown> = {},
): Promise<GateResult> {
  const r = await fetch(`/api/run/${command}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export interface RunStreamHandlers {
  onStart?: () => void;
  onLog?: (chunk: string) => void;
  onBusy?: (message: string) => void;
  onDone?: (code: number) => void;
  onError?: (message: string) => void;
}

/**
 * Stream a producer command's live output over SSE (`/api/run/<cmd>/stream`).
 * The server runs `garden <cmd>` under a pty and pushes output as it arrives.
 * Returns the EventSource so the caller can `.close()` to detach; call
 * `cancelRun()` to actually kill the underlying process.
 */
export function runCommandStream(command: RunCommand, h: RunStreamHandlers): EventSource {
  const es = new EventSource(`/api/run/${command}/stream`);
  let finished = false;
  const parse = (e: Event) => {
    try {
      return JSON.parse((e as MessageEvent).data) as Record<string, unknown>;
    } catch {
      return {};
    }
  };
  es.addEventListener("start", () => h.onStart?.());
  es.addEventListener("log", (e) => h.onLog?.(String(parse(e).chunk ?? "")));
  es.addEventListener("busy", (e) => h.onBusy?.(String(parse(e).error ?? "busy")));
  es.addEventListener("done", (e) => {
    finished = true;
    es.close();
    h.onDone?.(Number(parse(e).code ?? 0));
  });
  es.onerror = () => {
    if (finished) return; // normal close after `done`
    finished = true;
    es.close();
    h.onError?.("connection to the tend server was lost");
  };
  return es;
}

/** Kill the currently streaming producer, if any. */
export async function cancelRun(): Promise<GateResult> {
  const r = await fetch("/api/run/cancel", { method: "POST" });
  return r.json();
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
