<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import Chip from "@kit-ui/components/Chip.svelte";
  import EmptyState from "@kit-ui/components/EmptyState.svelte";
  import Markdown from "../components/Markdown.svelte";
  import GateActions from "../components/GateActions.svelte";
  import SplitView from "../components/SplitView.svelte";
  import RunButton from "../components/RunButton.svelte";
  import type { Proposal, RunCommand } from "../api";

  let {
    proposals,
    onDone,
    onRun,
    running,
  }: {
    proposals: Proposal[];
    onDone: () => void;
    onRun: (cmd: RunCommand) => void;
    running: RunCommand | null;
  } = $props();

  type Filter = "current" | "rejected" | "all";
  let filter = $state<Filter>("current");

  const counts = $derived({
    current: proposals.filter((p) => p.status === "current").length,
    rejected: proposals.filter((p) => p.status === "rejected").length,
    all: proposals.length,
  });
  const shown = $derived(
    filter === "all" ? proposals : proposals.filter((p) => p.status === filter),
  );
  const filters: { id: Filter; label: string }[] = [
    { id: "current", label: "Current" },
    { id: "rejected", label: "Rejected" },
    { id: "all", label: "All" },
  ];

  let selectedId = $state<string | null>(null);
  const selected = $derived(shown.find((p) => p.id === selectedId) ?? null);

  // Drop the selection if it falls out of the visible list (gate action or filter).
  $effect(() => {
    if (selectedId && !shown.some((p) => p.id === selectedId)) selectedId = null;
  });
</script>

<div class="filterbar">
  <div class="filterbar__filters" role="group" aria-label="Filter proposals">
    {#each filters as f}
      <button class="filter" aria-current={filter === f.id} onclick={() => (filter = f.id)}>
        {f.label}
        <span class="filter__count">{counts[f.id]}</span>
      </button>
    {/each}
  </div>
  <RunButton
    cmd="propose"
    label="Propose"
    title="Stage one atomic skill proposal from the wiki"
    {onRun}
    {running}
  />
</div>

{#if shown.length === 0}
  <EmptyState
    title={filter === "rejected" ? "No rejected proposals" : "No staged skill proposals"}
    description="Run `garden evolve` (or `garden propose`) to stage an atomic skill grounded in a wiki pattern."
  />
{:else}
  <SplitView open={selected !== null}>
    {#snippet list()}
      <Table ariaLabel="Skill proposals" stickyHeader>
        {#snippet header()}
          <TableHeaderCell label="Skill" />
          <TableHeaderCell label="Pattern" />
          <TableHeaderCell label="Staged" />
          <TableHeaderCell label="Gate" />
        {/snippet}
        {#each shown as p (p.id)}
          <tr
            class="wg-clickable"
            class:wg-selected={p.id === selectedId}
            onclick={() => (selectedId = p.id)}
          >
            <td><strong>{p.skill_name}</strong></td>
            <td class="wg-mono wg-dim">{p.pattern}</td>
            <td class="wg-dim">{p.staged_at.slice(0, 10)}</td>
            <td>
              {#if p.gate.human && p.gate.human !== "pending"}
                <Chip size="xs" tone={p.gate.human === "accepted" ? "success" : "danger"}>{p.gate.human}</Chip>
              {:else}
                <Chip size="xs" tone="warning">pending</Chip>
              {/if}
            </td>
          </tr>
        {/each}
      </Table>
    {/snippet}

    {#snippet detail()}
      {#if selected}
        <div class="detail">
          <div class="detail__head">
            <div>
              <div class="wg-dim wg-mono" style="font-size:.72rem">{selected.pattern}</div>
              <h3>{selected.skill_name}</h3>
            </div>
            <button class="detail__close" aria-label="Close" onclick={() => (selectedId = null)}>✕</button>
          </div>

          <p class="wg-muted">{selected.rationale}</p>

          {#if selected.status === "rejected"}
            <p class="wg-dim" style="font-size:.82rem">
              Rejected — archived and recorded in the skill-impact ledger; it won't be re-proposed.
            </p>
          {:else}
            <GateActions kind="proposals" id={selected.id} {onDone} />
          {/if}

          <details open>
            <summary>SKILL.md</summary>
            <Markdown source={selected.skill_md} frontmatter="preview" />
          </details>
          {#if selected.report}
            <details>
              <summary>Proposer report</summary>
              <p class="wg-muted">{selected.report}</p>
            </details>
          {/if}
        </div>
      {/if}
    {/snippet}
  </SplitView>
{/if}

<style>
  .filterbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--border-muted, rgba(0, 0, 0, 0.08));
  }
  .filterbar__filters {
    display: flex;
    gap: 0.3rem;
  }
  .filter {
    appearance: none;
    background: none;
    border: 1px solid transparent;
    border-radius: 999px;
    padding: 0.2rem 0.7rem;
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--text-secondary, #555);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .filter:hover {
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.05));
  }
  .filter[aria-current="true"] {
    background: var(--bg-inset, rgba(0, 0, 0, 0.06));
    border-color: var(--border-default, rgba(0, 0, 0, 0.15));
    color: var(--text-primary, #1a1a1a);
    font-weight: 600;
  }
  .filter__count {
    font-size: 0.72rem;
    color: var(--text-muted, #999);
  }
  .filter[aria-current="true"] .filter__count {
    color: inherit;
  }

  .detail {
    padding: 1rem 1.25rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }
  .detail__head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .detail__head h3 {
    margin: 0.1rem 0 0;
    font-size: 1.1rem;
  }
  .detail__close {
    appearance: none;
    background: none;
    border: none;
    font-size: 1rem;
    cursor: pointer;
    color: var(--text-muted, #888);
    padding: 0.2rem 0.4rem;
    border-radius: 6px;
  }
  .detail__close:hover {
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.06));
    color: var(--text-primary, #1a1a1a);
  }
  details {
    border-top: 1px solid var(--border-muted, rgba(0, 0, 0, 0.08));
    padding-top: 0.6rem;
  }
  summary {
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-secondary, #555);
    user-select: none;
  }
</style>
