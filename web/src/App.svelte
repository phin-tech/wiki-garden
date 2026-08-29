<script lang="ts">
  import Button from "@kit-ui/components/Button.svelte";
  import Notice from "@kit-ui/Notice.svelte";
  import { getSnapshot, type Snapshot } from "./api";
  import Proposals from "./views/Proposals.svelte";
  import Tools from "./views/Tools.svelte";
  import Patterns from "./views/Patterns.svelte";
  import Traces from "./views/Traces.svelte";
  import Evolution from "./views/Evolution.svelte";

  type TabId = "proposals" | "tools" | "patterns" | "traces" | "evolution";

  let snap = $state<Snapshot | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let tab = $state<TabId>("proposals");
  let dark = $state(document.documentElement.classList.contains("dark"));

  const tabs: { id: TabId; label: string; sub: string; glyph: string }[] = [
    { id: "proposals", label: "Proposals", sub: "Staged skills awaiting the gate", glyph: "◆" },
    { id: "tools", label: "Tools", sub: "Staged CLI tools awaiting review", glyph: "⌘" },
    { id: "patterns", label: "Patterns", sub: "The compiled wiki", glyph: "❖" },
    { id: "traces", label: "Traces", sub: "Raw captured sessions", glyph: "≣" },
    { id: "evolution", label: "Evolution", sub: "Impact ledger + log", glyph: "◵" },
  ];
  const active = $derived(tabs.find((t) => t.id === tab)!);
  const flush = $derived(tab === "proposals" || tab === "tools");

  async function load() {
    try {
      loading = true;
      error = null;
      snap = await getSnapshot();
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  function toggleTheme() {
    dark = !dark;
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("wg-theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }

  // Only the actionable sections badge, and only when something is gate-pending.
  function pending(id: TabId): number {
    if (!snap) return 0;
    if (id === "proposals") return snap.proposals.filter((p) => (p.gate.human ?? "pending") === "pending").length;
    if (id === "tools") return snap.tools.filter((t) => (t.gate.human ?? "pending") === "pending").length;
    return 0;
  }

  load();
</script>

<div class="app">
  <aside class="side">
    <div class="side__brand">🌱 <span>Wiki Garden</span></div>

    <nav class="side__nav" aria-label="Sections">
      {#each tabs as t}
        <button class="nav" aria-current={tab === t.id} onclick={() => (tab = t.id)}>
          <span class="nav__glyph" aria-hidden="true">{t.glyph}</span>
          <span class="nav__label">{t.label}</span>
          {#if pending(t.id) > 0}<span class="wg-badge">{pending(t.id)}</span>{/if}
        </button>
      {/each}
    </nav>

    <div class="side__spacer"></div>

    <div class="side__foot">
      {#if snap}<div class="side__store" title="store path">{snap.store}</div>{/if}
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="topbar__title">
        <h1>{active.label}</h1>
        <span class="topbar__sub">{active.sub}</span>
      </div>
      <div class="topbar__actions">
        <Button size="sm" surface="soft" onclick={toggleTheme}>{dark ? "☀︎ Light" : "☾ Dark"}</Button>
        <Button size="sm" surface="outline" onclick={load}>⟳ Refresh</Button>
      </div>
    </header>

    <section class="content" class:content--flush={flush}>
      {#if error}
        <div class="content__pad"><Notice tone="error">Couldn't reach the tend server: {error}</Notice></div>
      {:else if loading && !snap}
        <div class="content__pad"><p class="wg-muted">Loading the garden…</p></div>
      {:else if snap}
        {#if tab === "proposals"}
          <Proposals proposals={snap.proposals} onDone={load} />
        {:else if tab === "tools"}
          <Tools tools={snap.tools} onDone={load} />
        {:else if tab === "patterns"}
          <div class="content__pad"><Patterns patterns={snap.patterns} /></div>
        {:else if tab === "traces"}
          <div class="content__pad"><Traces traces={snap.traces} /></div>
        {:else if tab === "evolution"}
          <div class="content__pad"><Evolution evolution={snap.evolution} ledger={snap.ledger} /></div>
        {/if}
      {/if}
    </section>
  </main>
</div>
