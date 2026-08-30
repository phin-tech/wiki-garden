<script lang="ts">
  import type { RunEntry } from "../api";
  import RunEntryView from "./RunEntry.svelte";

  let {
    open = false,
    runs = [],
    onToggleEntry,
    onCancel,
    onClose,
    onClear,
  }: {
    open?: boolean;
    runs?: RunEntry[];
    onToggleEntry: (id: number) => void;
    onCancel: () => void;
    onClose: () => void;
    onClear: () => void;
  } = $props();

  const hasFinished = $derived(runs.some((r) => r.status !== "running"));
</script>

<aside class="rp" class:rp--open={open} aria-hidden={!open} aria-label="Command runs">
  <header class="rp__head">
    <span class="rp__title">Runs</span>
    {#if runs.length}<span class="rp__count">{runs.length}</span>{/if}
    <div class="rp__actions">
      {#if hasFinished}
        <button class="rp__act" onclick={onClear} title="Clear finished runs">Clear</button>
      {/if}
      <button class="rp__x" onclick={onClose} title="Hide panel" aria-label="Hide output panel">
        ✕
      </button>
    </div>
  </header>

  <div class="rp__list">
    {#if runs.length === 0}
      <p class="rp__empty">No runs yet — trigger a command and it'll stream here.</p>
    {:else}
      {#each runs as entry (entry.id)}
        <RunEntryView {entry} onToggle={() => onToggleEntry(entry.id)} {onCancel} />
      {/each}
    {/if}
  </div>
</aside>

<style>
  .rp {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: clamp(320px, 34vw, 460px);
    display: flex;
    flex-direction: column;
    background: var(--bg-primary, var(--bg-surface, #fafafa));
    border-left: var(--border-width, 1px) solid var(--border-default, #e0e0e0);
    box-shadow: -12px 0 32px rgba(0, 0, 0, 0.12);
    transform: translateX(100%);
    transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
    z-index: 40;
  }
  .rp--open {
    transform: translateX(0);
  }

  .rp__head {
    display: flex;
    align-items: center;
    gap: var(--space-2, 0.5rem);
    padding: var(--space-3, 0.7rem) var(--space-4, 0.9rem);
    border-bottom: var(--border-width, 1px) solid var(--border-default, #e0e0e0);
    flex: none;
  }
  .rp__title {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary, #1a1a1a);
  }
  .rp__count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.15rem;
    height: 1.15rem;
    padding: 0 0.35rem;
    border-radius: 999px;
    background: var(--bg-inset, rgba(0, 0, 0, 0.06));
    color: var(--text-secondary, #666);
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
  }
  .rp__actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: var(--space-1, 0.3rem);
  }
  .rp__act {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-secondary, #666);
    font-size: 0.75rem;
    padding: 0.2rem 0.45rem;
    border-radius: var(--radius-sm, 0.35rem);
  }
  .rp__act:hover {
    color: var(--text-primary, #111);
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.05));
  }
  .rp__x {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-muted, #888);
    font-size: 0.9rem;
    line-height: 1;
    padding: 0.2rem 0.35rem;
    border-radius: var(--radius-sm, 0.35rem);
  }
  .rp__x:hover {
    color: var(--text-primary, #111);
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.05));
  }

  .rp__list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--space-3, 0.7rem);
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 0.5rem);
  }
  .rp__empty {
    margin: auto;
    color: var(--text-muted, #999);
    font-size: 0.8rem;
    text-align: center;
    padding: var(--space-4, 0.9rem);
  }
</style>
