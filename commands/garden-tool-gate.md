---
description: Review staged Wiki Garden tools and accept or reject each — the human code-review gate. Tools are executable, so you MUST read the code before it goes on PATH.
argument-hint: [tool name, optional]
allowed-tools: Bash
---

You are running the **tool gate** for Wiki Garden. Tools are executables that
will land on the user's PATH, so a human must read the code. Never accept a tool
the user hasn't seen.

## 1. List staged tools

```bash
garden-tool-gate list
```

If a name was given in `$ARGUMENTS`, gate just that one; otherwise walk each.

## 2. Show the tool — manifest AND full source

```bash
garden-tool-gate show <name>
```

Present the source clearly and call out anything the reader must judge: what it
does, what it touches (AWS/DB/network), any destructive actions, required
credentials. Run the static safety review and relay it (advisory — it flags
secrets, unguarded destructive ops, injection, correctness; it never runs the
tool):

```bash
garden-tool-gate review <name>
```

## 3. Ask the user to decide

The user is the authority. Make sure they've actually seen the code. If they want
changes first, they can edit the staged executable before accepting.

On accept, also ask the **scope**: **global** (installed to `~/.local/bin`,
available everywhere) or **project** (committed into this repo's `bin/` +
`.claude/`, shared with the team, on PATH only where the repo's `bin/` is).
Suggest `project` for a tool tied to this repo's services; `global` for a
generally-useful tool.

## 4. Record the decision

```bash
# accept globally (default): store/tools + ~/.local/bin symlink + global catalog
garden-tool-gate accept <name> --note "<optional>"
# accept for THIS project only: committed into <repo>/bin + <repo>/.claude (add --project-dir if not in the repo)
garden-tool-gate accept <name> --scope project --note "<optional>"

# reject: records the decision (never re-mined) and archives the proposal
garden-tool-gate reject <name> --note "<why>"
```

Confirm the outcome: for an accept, tell the user the tool is on their PATH
(`<prefix><name>`) and they may need a new shell if `~/.local/bin` was just
created. Do not install a tool the user has not reviewed.
