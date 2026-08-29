<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import Chip from "@kit-ui/components/Chip.svelte";
  import EmptyState from "@kit-ui/components/EmptyState.svelte";
  import Markdown from "../components/Markdown.svelte";
  import GateActions from "../components/GateActions.svelte";
  import SplitView from "../components/SplitView.svelte";
  import type { Tool } from "../api";

  let { tools, onDone }: { tools: Tool[]; onDone: () => void } = $props();

  let selectedId = $state<string | null>(null);
  const selected = $derived(tools.find((t) => t.id === selectedId) ?? null);

  $effect(() => {
    if (selectedId && !tools.some((t) => t.id === selectedId)) selectedId = null;
  });
</script>

{#if tools.length === 0}
  <EmptyState
    title="No staged tools"
    description="Run `garden tool mine` or `garden tool capture --from <script>` to stage a reusable CLI tool for review."
  />
{:else}
  <SplitView open={selected !== null}>
    {#snippet list()}
      <Table ariaLabel="Staged tools" stickyHeader>
        {#snippet header()}
          <TableHeaderCell label="Name" />
          <TableHeaderCell label="Runtime" />
          <TableHeaderCell label="Executable" />
          <TableHeaderCell label="Staged" />
          <TableHeaderCell label="Gate" />
        {/snippet}
        {#each tools as t (t.id)}
          <tr class="wg-clickable" class:wg-selected={t.id === selectedId} onclick={() => (selectedId = t.id)}>
            <td><strong>{t.name}</strong></td>
            <td><Chip size="xs" tone="workspace">{t.runtime}</Chip></td>
            <td class="wg-mono wg-dim">{t.exe_name ?? "—"}</td>
            <td class="wg-dim">{t.staged_at.slice(0, 10)}</td>
            <td>
              {#if t.gate.human && t.gate.human !== "pending"}
                <Chip size="xs" tone={t.gate.human === "accepted" ? "success" : "danger"}>{t.gate.human}</Chip>
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
              <div class="wg-dim wg-mono" style="font-size:.72rem">{selected.runtime} · {selected.exe_name ?? ""}</div>
              <h3>{selected.name}</h3>
            </div>
            <button class="detail__close" aria-label="Close" onclick={() => (selectedId = null)}>✕</button>
          </div>

          <p class="wg-muted">{selected.description}</p>

          <GateActions kind="tools" id={selected.id} {onDone} />

          <details open>
            <summary>Source — read before accepting (this goes on your PATH)</summary>
            <pre class="wg-source">{selected.source}</pre>
          </details>
          <details>
            <summary>TOOL.md</summary>
            <Markdown source={selected.tool_md} />
          </details>
        </div>
      {/if}
    {/snippet}
  </SplitView>
{/if}

<style>
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
