<script lang="ts">
  import Table from "@kit-ui/components/Table.svelte";
  import TableHeaderCell from "@kit-ui/components/TableHeaderCell.svelte";
  import Chip from "@kit-ui/components/Chip.svelte";
  import Markdown from "../components/Markdown.svelte";
  import type { LedgerRow } from "../api";

  let { evolution, ledger }: { evolution: string; ledger: { skills: LedgerRow[]; tools: LedgerRow[] } } = $props();

  const rows = $derived(
    [
      ...ledger.skills.map((r) => ({ ...r, kind: "skill" })),
      ...ledger.tools.map((r) => ({ ...r, kind: "tool" })),
    ].sort((a, b) => String(b.date ?? "").localeCompare(String(a.date ?? ""))),
  );
</script>

<section>
  <h3 class="sec">Impact ledger <span class="wg-dim">· {rows.length}</span></h3>
  {#if rows.length === 0}
    <p class="wg-muted">No gate decisions recorded yet.</p>
  {:else}
    <Table ariaLabel="Impact ledger" stickyHeader>
      {#snippet header()}
        <TableHeaderCell label="Date" />
        <TableHeaderCell label="Kind" />
        <TableHeaderCell label="Item" />
        <TableHeaderCell label="Decision" />
        <TableHeaderCell label="Note" />
      {/snippet}
      {#each rows as r}
        <tr>
          <td class="wg-mono wg-dim">{r.date ?? ""}</td>
          <td>{r.kind}</td>
          <td class="wg-mono">{r.proposal ?? r.tool ?? ""}</td>
          <td>
            <Chip size="xs" tone={r.decision === "accepted" ? "success" : "danger"}>{r.decision ?? ""}</Chip>
          </td>
          <td class="wg-muted">{r.note ?? ""}</td>
        </tr>
      {/each}
    </Table>
  {/if}

  <h3 class="sec" style="margin-top:1.6rem">Evolution log</h3>
  <Markdown source={evolution || "_No evolution log yet._"} />
</section>

<style>
  .sec {
    font-size: 0.95rem;
    font-weight: 650;
    margin: 0 0 0.6rem;
  }
</style>
