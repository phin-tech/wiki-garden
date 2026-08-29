import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: false });

/** Render trusted-but-defensively-sanitized markdown (store content is local,
 * author-owned; we still sanitize to avoid surprises). */
export function renderMarkdown(src: string): string {
  const html = marked.parse(src ?? "", { async: false }) as string;
  return DOMPurify.sanitize(html);
}
