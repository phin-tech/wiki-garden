<script lang="ts">
  import Button from "@kit-ui/components/Button.svelte";
  import type { RunCommand } from "../api";

  let {
    cmd,
    label,
    title = undefined,
    onRun,
    running,
    surface = "soft",
    tone = "neutral",
  }: {
    cmd: RunCommand;
    label: string;
    title?: string;
    onRun: (cmd: RunCommand) => void;
    running: RunCommand | null;
    surface?: "soft" | "solid" | "outline";
    tone?: "neutral" | "workflow";
  } = $props();
</script>

<Button
  size="sm"
  {surface}
  {tone}
  {title}
  disabled={running !== null}
  onclick={() => onRun(cmd)}
>
  {running === cmd ? "⟳ " + label + "…" : label}
</Button>
