import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: false });

const FRONTMATTER_RE = /^﻿?---\r?\n([\s\S]*?)\r?\n---\r?\n?/;

/** Split a leading YAML frontmatter block off the body. `fm` is the inner YAML
 * (without the `---` fences), or null when there is none. */
export function splitFrontmatter(src: string): { fm: string | null; body: string } {
  const m = (src ?? "").match(FRONTMATTER_RE);
  if (!m) return { fm: null, body: src ?? "" };
  return { fm: m[1].trim(), body: (src ?? "").slice(m[0].length) };
}

/** Strip a leading YAML frontmatter block (`---` … `---`). Rendering it as raw
 * markdown is wrong: the closing `---` turns the lines above it into a setext
 * heading, so the whole block renders bold. Preview it as a code block instead. */
export function stripFrontmatter(src: string): string {
  return splitFrontmatter(src).body;
}

/** Render trusted-but-defensively-sanitized markdown (store content is local,
 * author-owned; we still sanitize to avoid surprises). */
export function renderMarkdown(src: string): string {
  const html = marked.parse(src ?? "", { async: false }) as string;
  return DOMPurify.sanitize(html);
}
