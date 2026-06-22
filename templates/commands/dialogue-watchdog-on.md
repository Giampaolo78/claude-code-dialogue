Arm the `<project>` watchdog: a background guardian for when you run instances and STEP AWAY. It watches for stuck requests (open REQ-IDs past threshold), dead instances (no lease + no activity), and a global freeze, and alerts the `system` board (+ a macOS popup when on a Mac). This is for UNATTENDED runs — an interactive session does NOT need it (the ALFA hooks already keep instances from going deaf). No preamble: arm it and confirm in one line.

## What to do (immediately)
1. Launch in BACKGROUND (run_in_background = true), from inside the project:
   ```
   dlg watchdog
   ```
   Optional: `--interval <sec>` (scan period) and `--threshold <sec>` (how long a request may stay open before a reminder). Defaults: 60s / 600s.
2. **Single-process by construction:** if a watchdog is already armed for this project, the command prints `[WATCHDOG] already running (pid X)` and does NOT start a second one — that's fine, nothing to do. Otherwise it prints `[WATCHDOG v2] active: ...`.
3. Confirm to the user in one line, e.g.: `Watchdog armed — alerts go to the system board + macOS popup.`

To stop it cleanly: `/dialogue-watchdog-off`.
