The user wants a TEAM RECAP/STANDUP: each WORKER Claude declares its status on ONE SHARED alignment board, then a round of cross-dependency comparison starts.

**WORKERS ONLY.** If you are a PROTOCOL/COORDINATION Claude (e.g. `claude-protocollo`): do NOT respond to this command, do NOT post a recap. You MONITOR the round and report to the boss (see `/dialogue-monitor-workers`) -- you don't take part.

`$ARGUMENTS` = YOUR worker name (e.g. `claude-backend` / `claude-dati` / `claude-frontend`); if empty, infer it from this window's domain.

## Steps

1. **Get the round's alignment board** (ATOMIC create-or-join, race-safe -- do NOT create it by hand):
   ```
   dlg recap-open <project>
   ```
   Prints `<board>\t<CREATED|JOINED>`. Use `<board>`: all workers of the same round converge on THIS one (the mechanism guarantees it, no race).

2. **If CREATED** (you are the round's initiator): leave a kickoff on `coordination` so the others know to post. If JOINED, skip this step.
   ```
   dlg say <project> coordination <NAME> "RECAP-ROUND open on <board>: post your status there (working-on / plan / blocked-by / pending)." --to all
   ```

3. **Post YOUR recap on the alignment board**, FIXED and COMPACT format (it's a snapshot, not an essay):
   ```
   dlg say <project> <board> <NAME> "<recap>" --to all
   ```
   - **WORKING-ON**: what you're doing NOW (1-2 lines).
   - **PLAN**: the next steps in order, each with status (todo / in-progress / done).
   - **BLOCKED-BY**: the standard markers `BLOCKED-BY: <agent> -- <activity> | UNBLOCK: <trigger>`, or "none".
   - **PENDING**: replies you're waiting for (from the boss or another Claude), with REQ-ID if any, or "none".

4. **COMPARE (not a monologue)**: read the others' recaps on the board and RECONCILE the cross-dependencies. If your BLOCKED-BY = another's deliverable, align the ETAs with a targeted reply (`--to <that-agent>`). This reconciliation IS the value of the round.

5. **Keep listening**. When the round is closed (everyone posted + dependencies aligned), the initiator archives the board: `dlg archive <project> <board>` (lifecycle).

## Rules
- TIGHT recap: snapshot, not essays. Anti-ceremony.
- ONE board per round: the atomic create-or-join guarantees it -> do NOT use `/dialogue-create-folder` here.
- Real comparison on the dependencies, not N disconnected parallel statuses.
- If you end a turn blocked, the markers (BLOCKED-BY / AWAITING HUMAN DECISION) also go IN CHAT with the boss, not only on the board.
