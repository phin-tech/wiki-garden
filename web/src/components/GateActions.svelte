<script lang="ts">
  import Button from "@kit-ui/components/Button.svelte";
  import Notice from "@kit-ui/Notice.svelte";
  import { gate, pickProject, type GateResult } from "../api";
  import { project, setProject } from "../project.svelte";

  let {
    kind,
    id,
    onDone,
  }: {
    kind: "proposals" | "tools";
    id: string;
    onDone: () => void;
  } = $props();

  let note = $state("");
  let scope = $state<"global" | "project">("global");
  let busy = $state<null | "accept" | "reject">(null);
  let result = $state<GateResult | null>(null);
  let browsing = $state(false);
  let pickerUnsupported = $state(false);

  async function browse() {
    browsing = true;
    try {
      const res = await pickProject(project.path);
      if (res.ok && res.path) setProject(res.path);
      else if (res.reason === "unsupported") pickerUnsupported = true;
    } catch {
      pickerUnsupported = true;
    } finally {
      browsing = false;
    }
  }

  const noun = $derived(kind === "proposals" ? "skill" : "tool");
  const projectReady = $derived(scope === "global" || Boolean(project.check?.ok));

  async function run(action: "accept" | "reject") {
    if (action === "reject" && !note.trim()) {
      result = { ok: false, error: "A reason is required to reject (it's recorded so the idea isn't re-proposed)." };
      return;
    }
    if (action === "accept" && scope === "project" && !project.check?.ok) {
      result = { ok: false, error: "Set a valid Project path in the sidebar before a project-scoped accept." };
      return;
    }
    busy = action;
    result = null;
    try {
      result = await gate(kind, id, action, {
        note: note.trim(),
        scope,
        project_dir: scope === "project" ? project.path : undefined,
      });
      if (result.ok) setTimeout(onDone, 900);
    } catch (e) {
      result = { ok: false, error: String(e) };
    } finally {
      busy = null;
    }
  }
</script>

<div class="gate">
  <label class="gate__note">
    <span>Note (required to reject)</span>
    <textarea
      bind:value={note}
      rows="2"
      placeholder="Why accept or reject? Recorded to the impact ledger."
      disabled={busy !== null}
    ></textarea>
  </label>

  <div class="gate__controls">
    <label class="gate__scope">
      <span>Scope</span>
      <select bind:value={scope} disabled={busy !== null}>
        <option value="global">global</option>
        <option value="project">project</option>
      </select>
    </label>
    {#if scope === "project"}
      <label class="gate__target">
        <span>Project path</span>
        <div class="gate__pathrow">
          <input
            type="text"
            spellcheck="false"
            placeholder="/abs/path/to/repo"
            value={project.path}
            disabled={busy !== null}
            oninput={(e) => setProject((e.currentTarget as HTMLInputElement).value)}
          />
          {#if !pickerUnsupported}
            <button type="button" class="gate__browse" disabled={busy !== null || browsing} onclick={browse}>
              {browsing ? "…" : "Browse…"}
            </button>
          {/if}
        </div>
        {#if project.path.trim() && project.check}
          <span class="gate__flag {project.check.ok ? 'ok' : 'no'}">
            {project.check.ok ? (project.check.git ? "✓ git repo" : "✓ dir") : `✕ ${project.check.reason}`}
          </span>
        {/if}
      </label>
    {/if}
    <span class="gate__spacer"></span>
    <Button tone="danger" surface="soft" size="sm" disabled={busy !== null} onclick={() => run("reject")}>
      {busy === "reject" ? "Rejecting…" : "Reject"}
    </Button>
    <Button
      tone="success"
      surface="solid"
      size="sm"
      disabled={busy !== null || !projectReady}
      onclick={() => run("accept")}
    >
      {busy === "accept" ? `Accepting ${noun}…` : `Accept ${noun}`}
    </Button>
  </div>

  {#if busy === "accept"}
    <p class="wg-muted">Running retro-eval / review — this can take a moment (it may call the LLM backend).</p>
  {/if}

  {#if result}
    {#if result.ok}
      <Notice tone="success">
        {noun[0].toUpperCase() + noun.slice(1)} {result.result?.decision ?? "done"}. Refreshing…
      </Notice>
    {:else}
      <Notice tone="error">{result.error ?? "Gate failed."}</Notice>
      {#if result.log}<pre class="wg-source">{result.log}</pre>{/if}
    {/if}
  {/if}
</div>

<style>
  .gate {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .gate__note {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.78rem;
    color: var(--text-secondary, #666);
  }
  .gate__note textarea {
    font: inherit;
    font-size: 0.85rem;
    padding: 0.5rem 0.6rem;
    border-radius: var(--radius-sm, 8px);
    border: 1px solid var(--border-default, rgba(0, 0, 0, 0.18));
    background: var(--bg-surface, #fff);
    color: var(--text-primary, #1a1a1a);
    resize: vertical;
  }
  .gate__controls {
    display: flex;
    align-items: flex-end;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .gate__scope {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.78rem;
    color: var(--text-secondary, #666);
  }
  .gate__scope select {
    font: inherit;
    padding: 0.35rem 0.5rem;
    border-radius: var(--radius-sm, 8px);
    border: 1px solid var(--border-default, rgba(0, 0, 0, 0.18));
    background: var(--bg-surface, #fff);
    color: var(--text-primary, #1a1a1a);
  }
  .gate__spacer {
    flex: 1;
  }
  .gate__target {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    min-width: 0;
    flex: 1;
    font-size: 0.78rem;
    color: var(--text-secondary, #666);
  }
  .gate__pathrow {
    display: flex;
    gap: 0.35rem;
    align-items: stretch;
  }
  .gate__target input {
    font: inherit;
    font-size: 0.8rem;
    font-family: var(--font-mono, ui-monospace, monospace);
    padding: 0.35rem 0.5rem;
    border-radius: var(--radius-sm, 8px);
    border: 1px solid var(--border-default, rgba(0, 0, 0, 0.18));
    background: var(--bg-surface, #fff);
    color: var(--text-primary, #1a1a1a);
    width: 100%;
    min-width: 0;
  }
  .gate__browse {
    appearance: none;
    font: inherit;
    font-size: 0.78rem;
    white-space: nowrap;
    padding: 0.35rem 0.6rem;
    border-radius: var(--radius-sm, 8px);
    border: 1px solid var(--border-default, rgba(0, 0, 0, 0.18));
    background: var(--bg-inset, rgba(0, 0, 0, 0.04));
    color: var(--text-primary, #1a1a1a);
    cursor: pointer;
  }
  .gate__browse:hover:not(:disabled) {
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.08));
  }
  .gate__browse:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .gate__flag {
    font-size: 0.7rem;
  }
  .gate__flag.ok { color: var(--accent-green, #16a34a); }
  .gate__flag.no { color: var(--accent-red, #dc2626); }
</style>
