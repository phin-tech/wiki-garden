---
description: Open the Wiki Garden web UI (`garden tend`) — browse patterns, traces, and the evolution log, and accept/reject staged skills and tools from the browser.
argument-hint: [--port N] [--host ADDR] [--no-open]
allowed-tools: Bash
---

Launch the Wiki Garden web UI by invoking the `tend` subcommand, forwarding any
arguments (`--port`, `--host`, `--no-open`):

```bash
garden tend $ARGUMENTS
```

`garden tend` starts a **long-running local HTTP server** (default
`http://127.0.0.1:8787`) and, unless `--no-open` is passed, opens it in the
browser. Because it blocks until stopped, **run it in the background** and then
report the URL to the user rather than waiting on it in the foreground.

Notes:
- If `garden` is not on PATH, use the skill's bundled launcher instead:
  `<skill-dir>/scripts/garden tend $ARGUMENTS` (it runs via `uv`, no install needed).
- The server serves the committed Svelte UI from the package's `web-dist/`; no JS
  toolchain is required at runtime.
- Accept/reject actions in the UI call the same in-process gate logic as
  `garden gate` / `garden tool gate`, so decisions stay consistent with the CLI.
- To stop it, the user (or you) can end the background process; mention that when
  you hand back the URL.
