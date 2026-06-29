#!/usr/bin/env bash
# ALFA Stop-hook (PLAN 0.6) - active enforcement of D1 (silent listener death, transient case).
#
# Installed by attach.sh into a project's .claude/settings.json on the "Stop" event, referenced by
# ABSOLUTE PATH to this file in the engine (so `git pull` updates it). It runs PER CLAUDE INSTANCE:
# at every Stop, Claude Code feeds a JSON on stdin and reads our exit code.
#
# Goal: an agent must not END a turn while ITS dialogue listener is dead (= silently deaf).
#   - listener alive            -> exit 0 (allow the stop)
#   - this session has no name   -> exit 0 (a non-dialogue Claude in the project must NEVER be blocked)
#   - listener DEAD              -> exit 2 + stderr "re-arm" (blocks the stop; Claude continues and
#                                   the stderr tells it to re-arm)
#
# DESIGN INVARIANTS:
#   * INSTANT: only reads a lease file + a mapping file. No wait, no freeze, no `claude` call.
#   * FAIL-OPEN: on ANY error/uncertainty -> exit 0. The hook must never trap the user.
#   * Loop-guard: honor stop_hook_active (worker2 safety 1). Claude Code's own block cap
#     (CLAUDE_CODE_STOP_HOOK_BLOCK_CAP, issue #55754) is the hard backstop on top of this.
#
# NB: the exact stop_hook_active / cap behaviour and the stdin field names are confirmed by
# rookie's E2E spike (cases DEAD / ALIVE / NO-MAPPING / BLOCK_CAP) before this goes live.
set -u

input="$(cat 2>/dev/null)" || exit 0
[ -z "$input" ] && exit 0

# Extract a top-level string field from the stdin JSON. python3 is already a tool dependency;
# if it is somehow absent, _field yields "" and every check below fails OPEN.
_field() {
    printf '%s' "$input" | python3 -c \
      "import sys,json
try:
    print(json.load(sys.stdin).get('$1',''))
except Exception:
    pass" 2>/dev/null
}

# --- Safety 1: do not re-block if Claude is already continuing because of a stop hook (loop-guard).
sha="$(_field stop_hook_active)"
case "$sha" in True|true|1) exit 0 ;; esac

# --- Resolve THIS session -> dialogue name.
sid="$(_field session_id)"
[ -z "$sid" ] && sid="$(basename "$(_field transcript_path)" .jsonl 2>/dev/null)"
case "$sid" in ""|*/*|*\\*|.|..) exit 0 ;; esac   # cannot identify the session -> fail-open (incl. Windows '\')

proj="$(_field cwd)"; [ -z "$proj" ] && proj="$PWD"

# --- Resolve dlg (PATH, then the standard symlink). Cannot probe -> fail-open.
dlg_bin="$(command -v dlg 2>/dev/null)"; [ -z "$dlg_bin" ] && dlg_bin="$HOME/.local/bin/dlg"
[ -x "$dlg_bin" ] || exit 0

# --- Resolve THIS session -> name THROUGH dlg itself, so it uses the SAME boards_root() walk-up as
# the binding write (a cwd in a project subdir can NEVER make the hook and the binding diverge).
# No binding for this session (e.g. a non-dialogue Claude) -> empty -> fail-open, never block.
name="$(cd "$proj" 2>/dev/null && "$dlg_bin" session-name "$sid" 2>/dev/null)"
[ -z "$name" ] && exit 0

# --- Instant liveness probe via dlg (single source of truth). Distinguish the exit code:
#   0  = listening               -> allow the stop
#   1  = not listening           -> block + tell the agent to re-arm
#   >1 = probe error / cd failed  -> FAIL-OPEN (never trap the user on our own bug)
(cd "$proj" 2>/dev/null && "$dlg_bin" is-listening "$name" >/dev/null 2>&1); rc=$?
case "$rc" in
    0) exit 0 ;;
    1) : ;;
    *) exit 0 ;;
esac

# --- DEAD: block the stop and tell the agent to re-arm (stderr is fed to Claude on exit 2).
echo "Your dialogue listener ('$name') is NOT running -> you would go silently deaf. Re-arm it NOW: run /dialogue-listen, OR launch the Bash tool with run_in_background=true running: $dlg_bin listen <project> coordination --name $name --timeout 1800 -- do NOT use shell '&' (not harness-tracked -> no wake). Then you may stop." >&2
exit 2