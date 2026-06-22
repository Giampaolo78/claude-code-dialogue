#!/bin/sh
# alfa-pretool-rearm.sh (PLAN 0.7) - active arm-first enforcement at EVERY tool call.
#
# Sibling of alfa-stop-rearm.sh (the Stop hook), but on the PreToolUse event: it runs BEFORE each
# tool call and, if the agent has gone deaf, BLOCKS the tool (exit 2) and tells it to re-arm first.
# Stop hook = "you can't END a turn deaf"; this = "you can't ACT while deaf". Together the agent is
# armed by construction between every action and at every stop -> the inert/not-reacting state goes.
#
# DESIGN INVARIANTS:
#   * FAST: the common path (agent IS listening) is PURE SHELL, no python spawn. python3 is used
#     only on the rare DEAF branch, to robustly read the tool command for the exemption.
#   * CHURN-TOLERANT: the one-shot listen dies on EVERY delivery; "no live lease" for a moment is
#     NORMAL, not deafness. We block only SUSTAINED deafness: NOT live AND NOT armed within GRACE.
#   * NO DEADLOCK: the re-arm is itself a tool call. We EXEMPT 'dlg ' commands so the agent can
#     always re-arm / read / reply even while deaf. Without this the first deaf agent freezes.
#   * FAIL-OPEN: on ANY error/uncertainty -> exit 0. The hook must never trap the user.
set -u

GRACE=25   # seconds: tolerate the normal deliver->rearm window; block only deafness past this.

input="$(cat 2>/dev/null)" || exit 0
[ -z "$input" ] && exit 0

# --- shell-pure extraction of a top-level JSON string field (no python on the common path).
_field() {
    printf '%s' "$input" | sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1
}

# --- resolve THIS session id.
sid="$(_field session_id)"
[ -z "$sid" ] && sid="$(basename "$(_field transcript_path)" .jsonl 2>/dev/null)"
case "$sid" in ""|*/*|*\\*|.|..) exit 0 ;; esac   # can't identify -> fail-open

# --- resolve the project root: walk up from cwd to the dir holding .dialogue (like dlg). Pure shell.
proj="$(_field cwd)"; [ -z "$proj" ] && proj="$PWD"
while [ "$proj" != "/" ] && [ ! -d "$proj/.dialogue" ]; do proj="$(dirname "$proj")"; done
[ -d "$proj/.dialogue" ] || exit 0   # not in a dialogue project -> fail-open

# --- resolve session -> name (real path boards/.sessions/). No binding -> non-dialogue Claude -> allow.
map="$proj/.dialogue/boards/.sessions/$sid"
[ -f "$map" ] || exit 0
name="$(cat "$map" 2>/dev/null)"
[ -z "$name" ] && exit 0

boards="$proj/.dialogue/boards"

# --- (1) is a LIVE listener lease present? pure shell; guard pid>0 (anticorpo worker2: os.kill/-0
#         with pid<=0 has special POSIX semantics and would false-positive 'alive').
for f in "$boards/.leases/$name".*.json; do
    [ -e "$f" ] || continue
    pid="$(basename "$f" | cut -d. -f2)"
    case "$pid" in ''|*[!0-9]*) continue ;; esac
    [ "$pid" -gt 0 ] 2>/dev/null || continue
    if kill -0 "$pid" 2>/dev/null; then exit 0; fi   # LISTENING -> allow
done

# --- (2) no live lease: is this the NORMAL deliver->rearm window? (armed within GRACE seconds)
mark="$boards/.last_arm/$name"
if [ -f "$mark" ]; then
    now="$(date +%s 2>/dev/null)"
    mt="$(stat -f %m "$mark" 2>/dev/null || stat -c %Y "$mark" 2>/dev/null)"
    if [ -n "$now" ] && [ -n "$mt" ] && [ "$((now - mt))" -lt "$GRACE" ]; then exit 0; fi
fi

# --- DEAF (no live lease AND not armed within GRACE). The re-arm ('dlg listen') is itself a Bash
# tool call, so mis-blocking a Bash would DEADLOCK the agent (it could never re-arm). We CANNOT
# reliably tell whether a given Bash is the re-arm: python3 may be off the hook's PATH, the command
# may be exotically quoted, etc. So we FAIL-OPEN on every Bash -- it might be the re-arm (or any
# dialogue command). We block only the OTHER tools (Read/Edit/Write/...), which forces a re-arm
# before non-trivial work; a pure-Bash deaf stretch is still caught at the turn end by the Stop hook
# (alfa-stop-rearm.sh). (worker2 anticorpo: gating Bash on python3 was a conditional deadlock.)
[ "$(_field tool_name)" = "Bash" ] && exit 0

# --- DEAF + a non-Bash tool -> BLOCK this tool call, force a re-arm first.
echo "You are NOT listening (re-arm was skipped) -> you would act while deaf. Re-arm FIRST: dlg listen <project> coordination --name $name --timeout 1800 . Then retry this action. (arm-first)" >&2
exit 2