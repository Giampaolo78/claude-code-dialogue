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
if [ -f "$SELF/templates/COORDINATION.template.md" ]; then
  sed "s#<project>#$NAME#g" "$SELF/templates/COORDINATION.template.md" > "$PROJ/.dialogue/COORDINATION.md"
fi

# 4) ALFA hooks: re-arm guards. ADDITIVE merge into .claude/settings.json -> never clobbers the
#    user's own hooks/settings. Idempotent. Referenced by ABSOLUTE PATH so a `git pull` of the
#    engine updates the hook scripts. Stop (0.6): can't END a turn deaf. PreToolUse (0.7): can't
#    ACT while deaf (arm-first before every tool call).
STOP_HOOK="$SELF/hooks/alfa-stop-rearm.sh"
PRE_HOOK="$SELF/hooks/alfa-pretool-rearm.sh"
if [ -x "$STOP_HOOK" ] && [ -x "$PRE_HOOK" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$PROJ/.claude/settings.json" "$STOP_HOOK" "$PRE_HOOK" <<'PYEOF' || echo "[attach] WARNING: ALFA hooks merge failed; settings.json left as-is"
import json, os, sys
settings_path, stop_hook, pre_hook = sys.argv[1], sys.argv[2], sys.argv[3]
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

def _present(groups, cmd):
    return any(
        isinstance(g, dict) and any(
            isinstance(h, dict) and h.get("command") == cmd for h in g.get("hooks", [])
        )
        for g in groups
    )

changed = False
stop = hooks.setdefault("Stop", [])
if isinstance(stop, list):
    if not _present(stop, stop_hook):
        stop.append({"hooks": [{"type": "command", "command": stop_hook}]}); changed = True
else:
    print("[attach] WARNING: settings.json hooks.Stop is not a list; Stop hook not installed")
pre = hooks.setdefault("PreToolUse", [])
if isinstance(pre, list):
    if not _present(pre, pre_hook):
        pre.append({"matcher": "*", "hooks": [{"type": "command", "command": pre_hook}]}); changed = True
else:
    print("[attach] WARNING: settings.json hooks.PreToolUse is not a list; PreToolUse hook not installed")

if changed:
    tmp = settings_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, settings_path)
    print("[attach] ALFA hooks installed in .claude/settings.json (Stop + PreToolUse, additive)")
else:
    print("[attach] ALFA hooks already present")
PYEOF
fi

echo "[attach] '$NAME' attached:"
echo "  - .dialogue/team (this project's isolated registry)"
echo "  - .dialogue/boards (isolated boards)"
echo "  - .dialogue/COORDINATION.md (protocol, <project> substituted)"
echo "  - $n commands in .claude/commands/"
echo "  - .claude/settings.json (ALFA Stop + PreToolUse hooks, additive merge)"
echo "Ready: open Claude here and use /dialogue-onboard."
