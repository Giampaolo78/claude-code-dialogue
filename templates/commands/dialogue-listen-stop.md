Stop THIS Claude instance's listening on the `<project>` dialogue system, CLEANLY. Mirror of /dialogue-listen. No analysis, no preamble: stop the listen and confirm in one line.

## Owner name
- If `$ARGUMENTS` is not empty: NAME = `$ARGUMENTS`.
- Otherwise infer from this window's domain: frontend -> `claude-frontend`; backend -> `claude-backend`; data -> `claude-dati`; coordination / gate -> `coordinator`; dialogue maintenance / protocol -> `claude-protocollo`.
- Only if you really can't tell who you are, ask once for the name and stop.

## What to do (immediately, nothing else)
1. Stop NAME's listener(s) with the AUTO-LOCATED subcommand `dlg unlisten` (clean SIGINT -> the listener's `finally` removes its lease, no zombies; + prunes the name's ALREADY-dead leases). No relative glob: paths are resolved from the wrapper's dir, not the cwd (DLG-002). Run (foreground):

   ```
   dlg unlisten <NAME>
   ```

2. Do NOT re-arm the listen: the listening loop ENDS here. If you have a harness background task for that listen, consider it concluded (the process has exited; ignore its completion task-notification).
3. Check (optional): `ls boards/.leases/<NAME>.*.json` must find nothing.
4. Confirm in ONE line: `Listen stopped (clean) for <NAME>. No longer listening.`

## Why SIGINT (and not kill/SIGTERM)
SIGINT becomes KeyboardInterrupt in Python: it propagates into `wait_inbox`'s try/finally, so the exiting process REMOVES its lease. SIGTERM/SIGKILL terminate without running the finally -> zombie lease (dead PID but file present) that pollutes the watchdog. That's why this command uses SIGINT (see DLG-001).

Replace `<NAME>` with the real value from the "Owner name" step.
