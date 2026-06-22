#!/usr/bin/env bash
# attach.sh [project-dir] - attach the dialogue to a project (default: cwd).
#
# Creates .dialogue/ (registry + boards ISOLATED for this project) and installs the Claude
# commands in .claude/commands/. Idempotent: re-running it updates the commands. Opt-in:
# the dialogue appears ONLY in the projects where you run attach.
set -euo pipefail

PROJ="${1:-$PWD}"
PROJ="$(cd "$PROJ" && pwd)"          # absolute
NAME="$(basename "$PROJ")"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # the engine home (where this script lives)
TPL="$SELF/templates/commands"

[ -d "$TPL" ] || { echo "[attach] ERROR: templates not found in $TPL"; exit 1; }

# 1) per-project state: isolated registry + boards inside the project
mkdir -p "$PROJ/.dialogue/team" "$PROJ/.dialogue/boards"
printf '%s\n' "$NAME" > "$PROJ/.dialogue/project"
# seed the registry with the right project name (otherwise the engine defaults to a generic
# name); does not overwrite an already-populated registry.
REG="$PROJ/.dialogue/team/registry.json"
[ -f "$REG" ] || printf '{\n  "project": "%s",\n  "members": []\n}\n' "$NAME" > "$REG"

# 2) Claude commands in the project (project name baked in, no <project> placeholder)
mkdir -p "$PROJ/.claude/commands"
n=0
for f in "$TPL"/*.md; do
  sed "s#<project>#$NAME#g" "$f" > "$PROJ/.claude/commands/$(basename "$f")"
  n=$((n+1))
done

# 3) coordination protocol in the project (project name substituted)
if [ -f "$SELF/templates/COORDINAMENTO.template.md" ]; then
  sed "s#<project>#$NAME#g" "$SELF/templates/COORDINAMENTO.template.md" > "$PROJ/.dialogue/COORDINAMENTO.md"
fi

# 4) ALFA Stop-hook (PLAN 0.6): re-arm guard. ADDITIVE merge into .claude/settings.json -> never
#    clobbers the user's own hooks/settings. Idempotent. Referenced by ABSOLUTE PATH so that a
#    `git pull` of the engine updates the hook script itself.
HOOK="$SELF/hooks/alfa-stop-rearm.sh"
if [ -x "$HOOK" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$PROJ/.claude/settings.json" "$HOOK" <<'PYEOF' || echo "[attach] WARNING: ALFA Stop-hook merge failed; settings.json left as-is"
import json, os, sys
settings_path, hook_cmd = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
try:
    with open(settings_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
except (FileNotFoundError, ValueError):
    data = {}
hooks = data.setdefault("hooks", {})
if not isinstance(hooks, dict):
    print("[attach] WARNING: settings.json 'hooks' is not an object; ALFA not installed"); sys.exit(0)
stop = hooks.setdefault("Stop", [])
if not isinstance(stop, list):
    print("[attach] WARNING: settings.json hooks.Stop is not a list; ALFA not installed"); sys.exit(0)
present = any(
    isinstance(g, dict) and any(
        isinstance(h, dict) and h.get("command") == hook_cmd for h in g.get("hooks", [])
    )
    for g in stop
)
if present:
    print("[attach] ALFA Stop-hook already present"); sys.exit(0)
stop.append({"hooks": [{"type": "command", "command": hook_cmd}]})
tmp = settings_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
os.replace(tmp, settings_path)
print("[attach] ALFA Stop-hook installed in .claude/settings.json (additive)")
PYEOF
fi

echo "[attach] '$NAME' attached:"
echo "  - .dialogue/team (this project's isolated registry)"
echo "  - .dialogue/boards (isolated boards)"
echo "  - .dialogue/COORDINAMENTO.md (protocol, <project> substituted)"
echo "  - $n commands in .claude/commands/"
echo "  - .claude/settings.json (ALFA Stop-hook, additive merge)"
echo "Ready: open Claude here and use /dialogue-onboard."
