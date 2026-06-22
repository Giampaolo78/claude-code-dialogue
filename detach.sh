#!/usr/bin/env bash
# detach.sh [project-dir] - detach the dialogue from the project (default: cwd).
#
# Removes the dialogue slash-commands from .claude/commands/ (the dialogue disappears from
# Claude's menu in this project). The DATA stays (.dialogue/: roster, messages, COORDINATION):
# detach is REVERSIBLE (a new `dlg attach` puts the commands back). To delete the data too:
# rm -rf <project>/.dialogue
set -euo pipefail

PROJ="${1:-$PWD}"
PROJ="$(cd "$PROJ" && pwd)"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # engine home
TPL="$SELF/templates/commands"

n=0
if [ -d "$TPL" ]; then
  for f in "$TPL"/*.md; do
    b="$(basename "$f")"
    if [ -f "$PROJ/.claude/commands/$b" ]; then rm -f "$PROJ/.claude/commands/$b"; n=$((n+1)); fi
  done
fi

echo "[detach] removed $n slash-commands from $PROJ/.claude/commands/"
if [ -d "$PROJ/.dialogue" ]; then
  echo "  The DATA stays in $PROJ/.dialogue/ (roster, messages, COORDINATION) -- detach is reversible."
  echo "  To delete it entirely:  rm -rf \"$PROJ/.dialogue\""
fi
