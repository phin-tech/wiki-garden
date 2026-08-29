---
description: Review staged Wiki Garden skill proposals and accept or reject each — the human-diff gate. Runs retro-eval, records the decision, and promotes accepted skills into skills/.
argument-hint: [proposal name, optional]
allowed-tools: Bash
---

You are running the **human-diff gate** for Wiki Garden. Present each staged
proposal to the user and record their decision — never decide for them.

## 1. List what's staged

```bash
garden-gate list
```

If a name was given in `$ARGUMENTS`, gate just that one; otherwise walk through
each staged proposal in turn.

## 2. Show the proposal

```bash
garden-gate show <name>
```

Present it clearly: the skill's purpose, the wiki pattern it traces back to
(PURPOSE.md), and the full SKILL.md. Optionally run retro-eval to inform the user
(advisory — it only fails on `harmful`, and skips when `eval/stash/` is empty):

```bash
garden-gate retro <name>
```

## 3. Ask the user to decide

Ask plainly: accept or reject? For a reject, get a one-line reason. Do NOT
pressure toward either; the user is the authority. If they want edits first, they
can tweak the staged `SKILL.md` before accepting.

On accept, also ask the **scope**: **global** (applies everywhere) or **project**
(only this repo, committable to `.claude/skills`, shareable with the team).
Suggest `project` when the skill encodes repo/stack-specific conventions, `global`
when it's broadly reusable.

## 4. Record the decision

```bash
# accept globally (default): store/skills + a ~/.claude/skills symlink
garden-gate accept <name> --note "<optional>"
# accept for THIS project only: committed into <repo>/.claude/skills (add --project-dir if not in the repo)
garden-gate accept <name> --scope project --note "<optional>"

# reject: appends a rejected record (so it is never re-proposed) and archives it
garden-gate reject <name> --note "<why>"
```

Then confirm the outcome to the user (what was promoted/installed, or that the
rejection was recorded). Accepted skills become active immediately for new
sessions; a reject is remembered by the proposer.
