---
description: Mine recent Wiki Garden traces for recurring/reusable command-line operations and stage them as tool proposals (the ambient path for the tools layer).
argument-hint: [--dry-run]
allowed-tools: Bash
---

Run the tool miner, forwarding any argument (e.g. `--dry-run`):

```bash
garden tool mine $ARGUMENTS
```

It scans unmined `raw/` traces for command-line operations that recur or are
clearly reusable, and stages each as a tool proposal by piping it through
`garden tool capture` (same generalization + secret-stripping + config runtime/overlays).
A cursor makes it incremental; existing and previously-rejected tools are skipped.

After it runs, summarize: which candidates it found and staged (or why nothing),
and remind the user that staged tools are ungated — review them with
`/garden-tool-gate` (read the code) before they go on PATH. Do not accept or
install anything here.
