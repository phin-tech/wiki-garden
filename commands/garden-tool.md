---
description: Capture a script the agent just used and turn it into a reusable, parameterized command-line tool — staged for gating, not installed. Part of Wiki Garden's tools layer.
argument-hint: [suggested tool name]
allowed-tools: Bash, Read
---

You are capturing a **Wiki Garden tool**: promoting an ephemeral script that just
proved useful into a durable, reusable CLI tool. Tools are staged for review —
never installed onto PATH until the user gates them.

## 1. Identify the script

Find the concrete script/command that just did the useful work this session — the
actual bash/python/node the agent wrote or ran (not a description of it). If it
lived in a scratch file, use that path; otherwise reconstruct the exact script.
Confirm with the user which script they want to keep if it's ambiguous.

## 2. Generalize + stage it

Pass the script to the capture runner. Prefer a file; otherwise pipe it:

```bash
garden-tool --from <path-to-script> --name "$ARGUMENTS"
# or, if it's not in a file:
printf '%s' "<the script>" | garden-tool --name "$ARGUMENTS"
```

Use `--runtime bash|uv|node` only if the user wants to override their configured
default. Add `--dry-run` first if you want to preview the generalized tool before
staging.

The runner asks an LLM to generalize the script — lift hardcoded values into
flags, strip any secrets (env/credential-chain instead), add `--help`, and target
the configured runtime — then stages `<store>/tool-proposals/<ts>_<name>/`
containing the executable, `TOOL.md`, and `PURPOSE.md`.

## 3. Show the result

Report what was staged: the tool name, its usage line, which values became args,
anything stripped (secrets), and any safety notes (destructive ops default to a
preview posture). Offer to show the generated executable so the user can read the
code. Do NOT install it or move it into `tools/` — gating happens separately.
