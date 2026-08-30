<script lang="ts">
  import Button from "@kit-ui/components/Button.svelte";
  import Notice from "@kit-ui/Notice.svelte";
  import {
    cancelRun,
    getSnapshot,
    runCommandStream,
    type RunCommand,
    type RunEntry,
    type Snapshot,
  } from "./api";
  import RunPanel from "./components/RunPanel.svelte";
  import Proposals from "./views/Proposals.svelte";
  import Tools from "./views/Tools.svelte";
  import Skills from "./views/Skills.svelte";
  import Patterns from "./views/Patterns.svelte";
  import Traces from "./views/Traces.svelte";
  import Evolution from "./views/Evolution.svelte";

  type TabId = "proposals" | "tools" | "skills" | "patterns" | "traces" | "evolution";

  let snap = $state<Snapshot | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let tab = $state<TabId>("proposals");
  let dark = $state(document.documentElement.classList.contains("dark"));

  const tabs: { id: TabId; label: string; sub: string; glyph: string }[] = [
    { id: "proposals", label: "Proposals", sub: "Staged skills awaiting the gate", glyph: "◆" },
    { id: "tools", label: "Tools", sub: "Staged CLI tools awaiting review", glyph: "⌘" },
    { id: "skills", label: "Skills", sub: "Activated skills in force", glyph: "✦" },
    { id: "patterns", label: "Patterns", sub: "The compiled wiki", glyph: "❖" },
    { id: "traces", label: "Traces", sub: "Raw captured sessions", glyph: "≣" },
    { id: "evolution", label: "Evolution", sub: "Impact ledger + log", glyph: "◵" },
  ];
  const active = $derived(tabs.find((t) => t.id === tab)!);
  const flush = $derived(tab === "proposals" || tab === "tools");

  // Producer commands are triggered from the tab they feed (see each view);
  // Evolve — maintain + propose in one — stays global in the top bar. Each run
  // is tracked as its own entry in the floating panel (a collapsible history),
  // so output from every command streams in one place and older runs stay
  // around to expand. The server serialises producers, so only one runs at once.
  let running = $state<RunCommand | null>(null);
  let panelOpen = $state(false);
  let runs = $state<RunEntry[]>([]);
  let seq = 0;
  let stream: EventSource | null = null;

  function run(cmd: RunCommand) {
    if (running) return;
    running = cmd;
    panelOpen = true;
    for (const r of runs) r.expanded = false; // collapse the previous runs
    runs = [
      { id: ++seq, cmd, log: "", status: "running", code: 0, startedAt: Date.now(), expanded: true },
      ...runs,
    ];
    const live = runs[0]; // the reactive proxy element — mutate through it
    stream = runCommandStream(cmd, {
      onLog: (chunk) => (live.log += chunk),
      onBusy: (msg) => {
        live.status = "busy";
        live.log += msg + "\n";
      },
      onDone: async (code) => {
        live.code = code;
        // A `busy` reply lands as done with code -1; keep the busy status.
        if (live.status !== "busy") live.status = code === 0 ? "done" : "error";
        running = null;
        stream = null;
        if (code === 0) await load();
      },
      onError: (msg) => {
        if (live.status === "running") {
          live.status = "error";
          live.log += `\n[${msg}]\n`;
        }
        running = null;
        stream = null;
      },
    });
  }

  function toggleEntry(id: number) {
    const r = runs.find((x) => x.id === id);
    if (r) r.expanded = !r.expanded;
  }

  function cancelActive() {
    void cancelRun(); // the stream ends with a done/error event that resets state
  }

  function clearFinished() {
    runs = runs.filter((r) => r.status === "running");
  }

  function togglePanel() {
    panelOpen = !panelOpen;
  }

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
        <Button
          size="sm"
          surface="solid"
          tone="workflow"
          disabled={running !== null}
          title="Compile new traces, then stage one skill proposal"
          onclick={() => run("evolve")}
        >
          {running === "evolve" ? "⟳ Evolve…" : "⟳ Evolve"}
        </Button>
        <span class="topbar__gap"></span>
        <Button
          size="sm"
          surface={panelOpen ? "soft" : "outline"}
          title={panelOpen ? "Hide the run panel" : "Show the run panel"}
          onclick={togglePanel}
        >
          <span class="topbar__runs">
            ▤ Runs{#if runs.length}<span class="topbar__runs-n">{runs.length}</span>{/if}{#if running}<span
                class="topbar__runs-live"
                aria-label="a command is running"
              ></span>{/if}
          </span>
        </Button>
        <Button size="sm" surface="soft" onclick={toggleTheme}>{dark ? "☀︎ Light" : "☾ Dark"}</Button>
        <Button size="sm" surface="outline" disabled={running !== null} onclick={load}>⟳ Refresh</Button>
      </div>
    </header>

    <section class="content" class:content--flush={flush}>
      {#if error}
        <div class="content__pad"><Notice tone="error">Couldn't reach the tend server: {error}</Notice></div>
      {:else if loading && !snap}
        <div class="content__pad"><p class="wg-muted">Loading the garden…</p></div>
      {:else if snap}
        {#if tab === "proposals"}
          <Proposals proposals={snap.proposals} onDone={load} onRun={run} {running} />
        {:else if tab === "tools"}
          <Tools tools={snap.tools} onDone={load} onRun={run} {running} />
        {:else if tab === "skills"}
          <div class="content__pad"><Skills skills={snap.skills} /></div>
        {:else if tab === "patterns"}
          <div class="content__pad"><Patterns patterns={snap.patterns} onRun={run} {running} /></div>
        {:else if tab === "traces"}
          <div class="content__pad"><Traces traces={snap.traces} /></div>
        {:else if tab === "evolution"}
          <div class="content__pad"><Evolution evolution={snap.evolution} ledger={snap.ledger} /></div>
        {/if}
      {/if}
    </section>
  </main>

  <RunPanel
    open={panelOpen}
    {runs}
    onToggleEntry={toggleEntry}
    onCancel={cancelActive}
    onClose={togglePanel}
    onClear={clearFinished}
  />
</div>
