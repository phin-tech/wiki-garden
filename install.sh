#!/usr/bin/env bash
# Dev install of Wiki Garden for the author's own machine. Symlinks everything so
# `git pull` here auto-updates installed copies. (End users can instead install
# just the skill via:  npx skills add phin-tech/wiki-garden)
#
#   skills/wiki-garden/scripts/*  -> ~/.local/bin/            (on PATH)
#   commands/*.md               -> ~/.claude/commands/       (slash commands)
#   agents/*.md                 -> ~/.claude/agents/         (subagents)
#   skills/wiki-garden            -> ~/.claude/skills/wiki-garden (skill discovery)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

link() { mkdir -p "$(dirname "$2")"; ln -sfn "$1" "$2"; echo "  $2 -> $1"; }

echo "installing from $repo"

echo "scripts (PATH):"
for f in "$repo"/skills/wiki-garden/scripts/*; do
  [[ -f "$f" && -x "$f" ]] || continue
  link "$f" "$HOME/.local/bin/$(basename "$f")"
done

echo "commands:"
for f in "$repo"/commands/*.md; do
  [[ -e "$f" ]] || continue
  link "$f" "$HOME/.claude/commands/$(basename "$f")"
done

echo "agents:"
for f in "$repo"/agents/*.md; do
  [[ -e "$f" ]] || continue
  link "$f" "$HOME/.claude/agents/$(basename "$f")"
done

echo "skill:"
link "$repo/skills/wiki-garden" "$HOME/.claude/skills/wiki-garden"

store="$("$repo/skills/wiki-garden/scripts/garden" home)"
echo "store: $store"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "note: add ~/.local/bin to PATH so the scripts resolve in shells" ;;
esac
echo "done."
