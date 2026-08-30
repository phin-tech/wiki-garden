<script lang="ts">
  import type { RunEntry } from "../api";

  let {
    entry,
    onToggle,
    onCancel,
  }: {
    entry: RunEntry;
    onToggle: () => void;
    onCancel: () => void;
  } = $props();

  let pre: HTMLPreElement | null = $state(null);
  let pinned = $state(true); // follow the tail unless the user scrolls up

  const running = $derived(entry.status === "running");
  const label = $derived(entry.cmd.replace("-", " "));

  const statusText = $derived(
    entry.status === "running"
      ? "running…"
      : entry.status === "busy"
        ? "busy"
        : entry.code === 0
          ? "done"
          : `exited ${entry.code}`,
  );

  function started(): string {
    return new Date(entry.startedAt).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function onScroll() {
    if (!pre) return;
    pinned = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 24;
  }

  // Follow the tail as output arrives, while expanded and not scrolled away.
  $effect(() => {
    void entry.log;
    if (pre && pinned && entry.expanded) pre.scrollTop = pre.scrollHeight;
  });
</script>

<div class="re" class:re--open={entry.expanded}>
  <button class="re__head" onclick={onToggle} aria-expanded={entry.expanded}>
    <span class="re__chev" aria-hidden="true">{entry.expanded ? "▾" : "▸"}</span>
    <span class="re__dot" data-status={entry.status} aria-hidden="true"></span>
    <code class="re__cmd">garden {label}</code>
    <span class="re__status">{statusText}</span>
    <span class="re__time">{started()}</span>
  </button>

  {#if entry.expanded}
    <pre class="re__log" bind:this={pre} onscroll={onScroll}>{entry.log || "waiting for output…"}</pre>
    {#if running}
      <div class="re__foot">
        <button class="re__stop" onclick={onCancel}>■ Stop</button>
        <span class="re__hint">streaming live</span>
      </div>
    {/if}
  {/if}
</div>

<style>
  .re {
    border: var(--border-width, 1px) solid var(--border-muted, #ececec);
    border-radius: var(--radius-md, 0.5rem);
    background: var(--bg-surface, #fff);
    overflow: hidden;
  }
  .re--open {
    border-color: var(--border-default, #e0e0e0);
  }

  .re__head {
    display: flex;
    align-items: center;
    gap: var(--space-2, 0.5rem);
    width: 100%;
    padding: var(--space-2, 0.5rem) var(--space-3, 0.7rem);
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    color: var(--text-primary, #1a1a1a);
    font: inherit;
  }
  .re__head:hover {
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.03));
  }
  .re__chev {
    color: var(--text-muted, #999);
    font-size: 0.7rem;
    width: 0.8rem;
    flex: none;
  }
  .re__dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: var(--radius-dot, 50%);
    background: var(--text-muted, #999);
    flex: none;
  }
  .re__dot[data-status="running"] {
    background: var(--accent-amber, #f5a623);
    animation: re-pulse 1s ease-in-out infinite;
  }
  .re__dot[data-status="done"] {
    background: var(--accent-green, #2ecc71);
  }
  .re__dot[data-status="error"],
  .re__dot[data-status="busy"] {
    background: var(--accent-red, #e74c3c);
  }
  @keyframes re-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }
  .re__cmd {
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
  }
  .re__status {
    color: var(--text-secondary, #666);
    font-size: 0.75rem;
  }
  .re__time {
    margin-left: auto;
    color: var(--text-muted, #999);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    flex: none;
  }

  .re__log {
    margin: 0;
    padding: var(--space-3, 0.7rem);
    max-height: 22rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
    font-size: 0.73rem;
    line-height: 1.45;
    color: var(--text-primary, #1a1a1a);
    background: var(--bg-inset, rgba(0, 0, 0, 0.03));
    border-top: var(--border-width, 1px) solid var(--border-muted, #ececec);
  }

  .re__foot {
    display: flex;
    align-items: center;
    gap: var(--space-2, 0.5rem);
    padding: var(--space-2, 0.5rem) var(--space-3, 0.7rem);
    border-top: var(--border-width, 1px) solid var(--border-muted, #ececec);
  }
  .re__stop {
    border: var(--border-width, 1px) solid var(--border-default, #e0e0e0);
    background: var(--bg-surface, #fff);
    color: var(--danger, #e74c3c);
    cursor: pointer;
    font-size: 0.74rem;
    font-weight: 600;
    padding: 0.24rem 0.55rem;
    border-radius: var(--radius-sm, 0.35rem);
  }
  .re__stop:hover {
    border-color: var(--danger, #e74c3c);
  }
  .re__hint {
    color: var(--text-muted, #999);
    font-size: 0.73rem;
  }
</style>
