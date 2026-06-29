Put THIS Claude instance into listening on the `<project>` dialogue system, and that's it. No analysis, no preamble: arm the listen and confirm in one line.

> **CRITICAL -- common fail mode #1.** Launch the listener via the Bash tool's `run_in_background=true` parameter, NOT shell `&`. Why: `&` is not harness-tracked -> no task-notification -> silent deafness across the next turn boundary (seen live after an auto-compact). `dlg status` may show `LISTENING` right after `&`, but the process dies at the turn boundary -- always re-arm with run_in_background=true.

> **CRITICAL -- common fail mode #2.** Launching a NEW background listener while the previous one is still alive **KILLS the old one** (the Bash tool keeps one background process per slot -- the new replaces the old). So: re-arm ONLY when the listener has actually exited (`<dlg> status` = not listening). If it is still `LISTENING`, do NOT launch another -- just poll your inbox with foreground `<dlg> inbox <NAME>`. Polling the inbox each turn is the resilient fallback; treat the wake as a bonus, not the only mechanism (messages are never lost -- they stay in the inbox).

## Owner name
- If `$ARGUMENTS` is not empty: NAME = `$ARGUMENTS`.
- Otherwise infer from this window's domain: frontend -> `claude-frontend`; backend -> `claude-backend`; data -> `claude-dati`; coordination / gate -> `coordinator`.
- Only if you really can't tell who you are, ask once for the name and stop.

## What to do (immediately, nothing else)
1. Launch in BACKGROUND (run_in_background = true) exactly this:

   ```
   <dlg> listen <project> coordination --name <NAME> --timeout 1800
   ```

   The listen is a GLOBAL cursor: it wakes you for EVERY message addressed to {all, <NAME>} on any board (not just `coordination`).
2. **VERIFY — prove it, don't claim it** (this is the fix for "I said I was listening but I wasn't"):
   - The background launch returns immediately. Run `<dlg> status` and read YOUR line.
   - **`LISTENING (pid X)`** -> confirm in ONE line WITH the proof: `Listening as <NAME> — pid X confirmed.`
   - **`not listening`** -> the listen already exited. Usually it delivered a PENDING message (that is fine): read its output (or `<dlg> inbox <NAME>`), handle the messages, then **re-arm** and run `<dlg> status` again. Once it shows `LISTENING (pid X)`, confirm with the pid.
   - If after a re-arm with an EMPTY inbox it STILL shows `not listening`, do NOT claim you are listening: report `WARNING: listen is not staying armed` and stop for the user.

## When the listen exits (you get the task-notification: message received, or a 1800s empty timeout)
- If there are new messages: the listen WAKES you AND shows the new messages' content directly in its output. (They also stay in your inbox -- the listen does NOT consume them -- so even if you miss the output you recover them with `<dlg> inbox <NAME>`, which shows ALL your unread and does NOT consume: you can re-run it and see the same ones, impossible to miss one.) Handle them IN YOUR DOMAIN, and ONLY when done mark them read with `<dlg> inbox <NAME> --done`. To reply: `<dlg> say <project> coordination <NAME> "text" --to <dest>`.
- Then re-arm the same listen command in background (the listener has exited, so it is dead -- launching a new one is safe).

You stay listening in a continuous loop, until the user tells you to stop. A user question or a new task does NOT interrupt listening. At the end of a turn, do NOT blindly re-arm: run `<dlg> status` first -- if it says `LISTENING`, leave it (a new background listener would KILL it) and just poll `<dlg> inbox <NAME>`; re-arm ONLY if it says not-listening.

## NEVER auto-claim your listening state — the ONLY authority is `<dlg> status`
Do not write "Listening", "listen alive", or ANY claim about your own listening state in prose — board posts, sign-offs, syntheses, chat to the user — from memory or intention. The listener is one-shot and can die a moment after you launch it: "I just ran `<dlg> listen`, so I'm listening" is FALSE the instant it exits. If you must report your state, run `<dlg> status` FIRST and quote it (`LISTENING (pid X)` or `not listening`). A claim not backed by a fresh `<dlg> status` is a lie, even if you believe it. **Prove it, never declare it.**
