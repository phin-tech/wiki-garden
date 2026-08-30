<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import EmptyState from "@kit-ui/components/EmptyState.svelte";
  import DetailDrawer from "@kit-ui/components/DetailDrawer.svelte";
  import Markdown from "../components/Markdown.svelte";
  import RunButton from "../components/RunButton.svelte";
  import type { Pattern, RunCommand } from "../api";

  let {
    patterns,
    onRun,
    running,
  }: { patterns: Pattern[]; onRun: (cmd: RunCommand) => void; running: RunCommand | null } = $props();
  let open = $state<Pattern | null>(null);
</script>

<div class="wg-actions">
  <RunButton
    cmd="maintain"
    label="Maintain"
    title="Compile new traces into wiki patterns"
    {onRun}
    {running}
  />
</div>

{#if patterns.length === 0}
  <EmptyState
    title="No wiki patterns yet"
    description="Capture traces with /wiki-garden, then run `garden maintain` to compile them into patterns."
  />
{:else}
  <Table ariaLabel="Wiki patterns" stickyHeader>
    {#snippet header()}
      <TableHeaderCell label="Pattern" />
      <TableHeaderCell label="Id" />
      <TableHeaderCell label="Updated" />
    {/snippet}
    {#each patterns as p (p.id)}
      <tr class="wg-clickable" onclick={() => (open = p)}>
        <td><strong>{p.title}</strong></td>
        <td class="wg-mono wg-dim">{p.id}</td>
        <td class="wg-dim">{p.updated_at.slice(0, 10)}</td>
      </tr>
    {/each}
  </Table>
{/if}

{#if open}
  <DetailDrawer title={open.title} width="640px" onclose={() => (open = null)}>
    <Markdown source={open.body} />
  </DetailDrawer>
{/if}
