<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import EmptyState from "@kit-ui/components/EmptyState.svelte";
  import DetailDrawer from "@kit-ui/components/DetailDrawer.svelte";
  import Markdown from "../components/Markdown.svelte";
  import type { Trace } from "../api";

  let { traces }: { traces: Trace[] } = $props();
  let open = $state<Trace | null>(null);
</script>

{#if traces.length === 0}
  <EmptyState
    title="No traces captured"
    description="Run /wiki-garden after a task to capture a structured trace of what worked and what failed."
  />
{:else}
  <Table ariaLabel="Raw traces" stickyHeader>
    {#snippet header()}
      <TableHeaderCell label="Trace" />
      <TableHeaderCell label="Captured" />
    {/snippet}
    {#each traces as t (t.id)}
      <tr class="wg-clickable" onclick={() => (open = t)}>
        <td class="wg-mono"><strong>{t.id}</strong></td>
        <td class="wg-dim">{t.captured_at.slice(0, 16).replace("T", " ")}</td>
      </tr>
    {/each}
  </Table>
{/if}

{#if open}
  <DetailDrawer title={open.id} width="720px" onclose={() => (open = null)}>
    <Markdown source={open.body} />
  </DetailDrawer>
{/if}
