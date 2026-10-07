#!/usr/bin/env bash
# Installs hooks, agents, skills, the token-weather mod and the reference doc into
# ~/.claude, creates the memory dir, and merges settings.snippet.json into
# ~/.claude/settings.json (existing values win; a backup is written first).
# Existing files are backed up before being replaced. CLAUDE.md is never overwritten.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CC="$HOME/.claude"
SLUG="$(echo "$HOME" | tr '/' '-')"
MEM="$CC/projects/$SLUG/memory"
STAMP="$(date +%Y%m%d-%H%M%S)"

install_file() { # src dest
  mkdir -p "$(dirname "$2")"
  if [[ -f "$2" ]] && ! cmp -s "$1" "$2"; then
    cp "$2" "$2.bak-$STAMP"
    echo "backed up $2"
  fi
  cp "$1" "$2"
}

cd "$SRC"
while IFS= read -r f; do
  install_file "$f" "$CC/$f"
  case "$f" in hooks/*.py|hooks/*.sh) chmod +x "$CC/$f" ;; esac
  echo "installed $f"
done < <(find hooks agents skills mods reference -type f ! -name '.DS_Store' ! -path '*/__pycache__/*' | sort)

mkdir -p "$CC/plan-gates" "$MEM/.session-logs"
cp -n plan-gates/example.json.disabled "$CC/plan-gates/" 2>/dev/null || true

if [[ ! -f "$MEM/MEMORY.md" ]]; then
  cp memory/MEMORY.md "$MEM/MEMORY.md"
  echo "created $MEM/MEMORY.md"
fi

if [[ -f "$CC/CLAUDE.md" ]]; then
  echo "kept your existing $CC/CLAUDE.md (template is at $SRC/CLAUDE.md)"
else
  cp CLAUDE.md "$CC/CLAUDE.md"
  echo "installed CLAUDE.md -- replace <YOUR NAME> in it"
fi

python3 "$SRC/merge-settings.py" "$CC/settings.json"

echo
echo "Done. Next:"
echo "  1. Edit ~/.claude/CLAUDE.md (your name, your rules)"
echo "  2. touch ~/.claude-bell   # optional: sound when a turn finishes"
echo "  3. Restart your Claude Code sessions"
