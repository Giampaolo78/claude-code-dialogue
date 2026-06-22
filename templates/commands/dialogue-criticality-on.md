You've made a DISCOVERY / spotted a CRITICAL ISSUE that the colleagues need to know about and that needs a ROUND OF COMPARISON. Open a dedicated thread and bring them to the comparison -- no monologue, it's a multi-headed negotiation. `$ARGUMENTS` = YOUR name (e.g. `claude-protocollo`); if empty, infer it from this window's domain.

## What to do (in order)

1. **Focus the critical issue** (from your current session): what you discovered, WHY it's critical, WHAT you need from the team (a comparison / a design decision / a check in their domain), and the specific OPEN-QUESTIONS. Choose a **short** (brief slug, 2-4 words) that names it.

2. **Open a dedicated board** with the short: run `/dialogue-create-folder <critical-short>` (creates the board + timestamp). Note the exact NAME created -- the NAME itself (the short) IS already the scope, visible in `dlg status`. The detailed scope goes in the first post (step 3). NB: there is NO per-board topic (`dlg topic` is per-CONV, not per-board) -- don't use it.

3. **Post the critical issue on the new board**, addressed ONLY to the owners who must compare on it (`--to <owner>`; `--to all` only if it concerns everyone). Message structure:
   - **DISCOVERY**: what you found (concrete, with where/how you saw it).
   - **WHY CRITICAL**: the impact if not handled.
   - **WHAT I ASK THE TEAM**: the precise comparison/decision needed.
   - **OPEN-QUESTION**: specific, so they know exactly what to answer.
   ```
   dlg say <project> <board> <NAME> "<DISCOVERY / WHY CRITICAL / WHAT I ASK / OPEN-QUESTION>" --to <owner|all>
   ```

4. **Leave a pointer on `coordination`** so they know the thread exists (the dedicated board doesn't wake them more, but they need to know to go there):
   ```
   dlg say <project> coordination <NAME> "Opened board <board> for the critical issue: <short> -> comparison there." --to <owner|all>
   ```

5. **Keep listening** to the comparison (arm/keep the listen armed). When the round CONVERGES: SYNTHESIZE the outcome on the board. If the outcome requires a boss decision, close with the marker `>>> BLOCKED — AWAITING HUMAN DECISION: <the choice> <<<` -- and remember: the marker goes IN CHAT with the boss, not only on the board.

## Rules
- One critical issue = one board = one scope. Do NOT mix multiple themes in the same one.
- Bring the COMPARISON, not a monologue: explicitly ASK the opinion of the owners touched. The multi-headed negotiation IS the value (it catches the blind-spots you don't see alone).
- Honesty: also say what you do NOT know / where you might be wrong.
- When the theme is closed: archive the board with `dlg archive <project> <board>` (lifecycle: don't leave it to rot).
