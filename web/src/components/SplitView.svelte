<script lang="ts">
  import type { Snippet } from "svelte";
  import SplitResizeHandle from "@kit-ui/components/SplitResizeHandle.svelte";
  import type { SplitResizeEvent } from "@kit-ui/components/split-resize";

  let {
    list,
    detail,
    open = false,
    min = 320,
    max = 720,
  }: {
    list: Snippet;
    detail: Snippet;
    open?: boolean;
    min?: number;
    max?: number;
  } = $props();

  let listWidth = $state(440);
  let base = 440;

  function clamp(w: number) {
    return Math.max(min, Math.min(max, w));
  }
  function onStart() {
    base = listWidth;
  }
  function onResize(e: SplitResizeEvent) {
    listWidth = clamp(base + e.delta);
  }
</script>

<div class="split" class:split--open={open}>
  <div class="split__list" style={open ? `width:${listWidth}px` : undefined}>
    {@render list()}
  </div>
  {#if open}
    <SplitResizeHandle
      ariaLabel="Resize list"
      ariaValueMin={min}
      ariaValueMax={max}
      ariaValueNow={listWidth}
      onResizeStart={onStart}
      onResize={onResize}
    />
    <div class="split__detail">
      {@render detail()}
    </div>
  {/if}
</div>

<style>
  .split {
    display: flex;
    height: 100%;
    min-height: 0;
  }
  .split__list {
    flex: 1;
    min-width: 0;
    overflow: auto;
  }
  .split--open .split__list {
    flex: none;
  }
  .split__detail {
    flex: 1;
    min-width: 0;
    overflow: auto;
    border-left: 1px solid var(--border-muted, rgba(0, 0, 0, 0.1));
    background: var(--bg-surface, #fff);
  }
</style>
