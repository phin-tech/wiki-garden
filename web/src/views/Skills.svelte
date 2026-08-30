<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import EmptyState from "@kit-ui/components/EmptyState.svelte";
  import DetailDrawer from "@kit-ui/components/DetailDrawer.svelte";
  import Chip from "@kit-ui/components/Chip.svelte";
  import Markdown from "../components/Markdown.svelte";
  import type { Skill } from "../api";

  let { skills }: { skills: Skill[] } = $props();
  let open = $state<Skill | null>(null);
</script>

{#if skills.length === 0}
  <EmptyState
    title="No activated skills yet"
    description="Accepted proposals land here. Review staged proposals in the gate, then accept one to activate it as a skill."
  />
{:else}
  <Table ariaLabel="Activated skills" stickyHeader>
    {#snippet header()}
      <TableHeaderCell label="Skill" />
      <TableHeaderCell label="Ver" />
      <TableHeaderCell label="What it does" />
      <TableHeaderCell label="Activated" />
    {/snippet}
    {#each skills as s (s.id)}
      <tr class="wg-clickable" onclick={() => (open = s)}>
        <td><strong>{s.name}</strong></td>
        <td>
          {#if s.version > 1}
            <Chip size="xs" tone="info">v{s.version}</Chip>
          {:else}
            <Chip size="xs">v{s.version}</Chip>
          {/if}
          {#if s.revisions > 0}<span class="wg-dim" style="font-size:.72rem"> · {s.revisions} prior</span>{/if}
        </td>
        <td class="wg-dim">{s.description}</td>
        <td class="wg-dim">{s.activated_at.slice(0, 10)}</td>
      </tr>
    {/each}
  </Table>
{/if}

{#if open}
  <DetailDrawer title={open.name} width="640px" onclose={() => (open = null)}>
    <Markdown source={open.body} frontmatter="preview" />
  </DetailDrawer>
{/if}
