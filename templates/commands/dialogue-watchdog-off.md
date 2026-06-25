Stop the `<project>` watchdog (the one armed with `/dialogue-watchdog-on`). No preamble.

## What to do
1. Run:
   ```
   <dlg> watchdog-stop
   ```
2. It prints `[WATCHDOG] stopped (pid X).` — it sent SIGTERM to the running watchdog and dropped its lease — or `[WATCHDOG] not running.` if nothing was armed. Confirm to the user in one line.
