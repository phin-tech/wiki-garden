<script lang="ts">
  import { renderMarkdown, splitFrontmatter } from "../markdown";
  // frontmatter: "preview" shows it as a YAML code block; "hide" strips it.
  let { source = "", frontmatter = "raw" }: {
    source?: string;
    frontmatter?: "raw" | "preview" | "hide";
  } = $props();
  const html = $derived.by(() => {
    if (frontmatter === "raw") return renderMarkdown(source);
    const { fm, body } = splitFrontmatter(source);
    if (frontmatter === "hide" || !fm) return renderMarkdown(body);
    return renderMarkdown("```yaml\n" + fm + "\n```\n\n" + body);
  });
</script>

<!-- eslint-disable-next-line svelte/no-at-html-tags — sanitized in renderMarkdown -->
<div class="md">{@html html}</div>

<style>
  .md :global(h1),
  .md :global(h2),
  .md :global(h3) {
    margin: 1.1em 0 0.5em;
    line-height: 1.25;
  }
  .md :global(h1) { font-size: 1.3rem; }
  .md :global(h2) { font-size: 1.1rem; }
  .md :global(h3) { font-size: 1rem; }
  .md :global(p),
  .md :global(ul),
  .md :global(ol) { margin: 0.5em 0; }
  .md :global(li) { margin: 0.2em 0; }
  .md :global(code) {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.86em;
    background: var(--bg-surface-hover, rgba(0, 0, 0, 0.05));
    padding: 0.1em 0.34em;
    border-radius: 5px;
  }
  .md :global(pre) {
    background: var(--bg-inset, rgba(0, 0, 0, 0.05));
    border: 1px solid var(--border-muted, rgba(0, 0, 0, 0.1));
    border-radius: 10px;
    padding: 0.85em 1em;
    overflow-x: auto;
  }
  .md :global(pre code) { background: none; padding: 0; }
  .md :global(a) { color: var(--accent-blue, #2563eb); }
  .md :global(blockquote) {
    margin: 0.6em 0;
    padding-left: 0.9em;
    border-left: 3px solid var(--border-default, rgba(0, 0, 0, 0.15));
    color: var(--text-secondary, #555);
  }
</style>
