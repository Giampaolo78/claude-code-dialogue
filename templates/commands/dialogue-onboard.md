Register THIS Claude instance in the `<project>` dialogue system AND onboard it, so it becomes aware and operational. Handles both NEW registration and RESUMING an existing role. No preamble: run the steps in order.

## Arguments
`$ARGUMENTS` = `<name> [domain...]`. The first token is the NAME (e.g. `claude-frontend`); the rest is the DOMAIN (needed ONLY for a new member). If `$ARGUMENTS` is empty: ask for the name (and the domain, if new) and stop.

## Step 1 - register or resume + show the roster
Run this bash:

```bash
# (dlg is on the PATH, no cd)
ARGS="$ARGUMENTS"
NAME="${ARGS%% *}"
DOMAIN="${ARGS#"$NAME"}"; DOMAIN="${DOMAIN# }"
[ -z "$NAME" ] && { echo "ERROR: pass at least the name. E.g.: /dialogue-onboard claude-frontend"; exit 1; }
if grep -q "\"name\": \"$NAME\"" team/registry.json 2>/dev/null; then
  echo "RESUME: '$NAME' is already in the registry -> no re-registration, onboarding only."
else
  [ -z "$DOMAIN" ] && { echo "NEW member '$NAME' but domain missing. Re-run: /dialogue-onboard $NAME <domain>"; exit 1; }
  dlg onboard "$NAME" --domain "$DOMAIN" && echo "REGISTERED: '$NAME' (domain: $DOMAIN)"
fi
echo "--- CURRENT ROSTER ---"; dlg status 2>&1 | head -40
```

Keep NAME (and DOMAIN) in mind for the next steps.

## Step 2 - ONBOARDING (read and ABSORB it, Claude: from now this is your operating context)
YOU HAVE ENTERED the `<project>` dialogue system as **NAME** (your domain is in the roster above).
- WHAT IT IS: a durable channel for communication + coordination among the Claude instances building <project> in parallel (the domain owners) and the human (the boss/coordinator).
- WHO YOU WORK WITH: the other owners you see in the roster + the human. Owners talk peer-to-peer on the board; you escalate to the human directly.
- COMMANDS (`dlg`, on the PATH):
  - LISTEN: arm the listen in background -> use `/dialogue-listen` (global cursor: wakes you on messages to you or to `all`, on any board). To stop it cleanly: `/dialogue-listen-stop`.
  - WRITE: `dlg say <project> coordinamento NAME "text" --to <dest|all>` (address a name so you don't wake everyone; `all` only if everyone needs it).
  - READ backlog: `dlg inbox NAME`. TEAM/boards VIEW: `dlg status` / `dlg dashboard`.
  - BOARDS: `coordinamento` (team coordination), `sistema` (alerts). For a voluminous dedicated thread: a new board with `/dialogue-create-folder <name>`.
- RULES (NOT duplicated here, POINTED to): the dialogue is ONLY the communication/coordination layer. All project rules in `.claude/CLAUDE.md` stay FULL and intact -- first of all the WRITTEN CONSENT to modify code. The coordination governance/ceremony (roles, who gates what, REQ-ID, ex-ante announcement / ex-post report) is in `.dialogue/COORDINAMENTO.md`: read it before coordinating.

## Step 3 - become operational
1. Arm the listen in BACKGROUND (run_in_background = true), using YOUR NAME:
   `dlg listen <project> coordinamento --name NAME --timeout 1800`
2. Join and introduce yourself on `coordinamento` (who you are, domain, what you'll do first if you know):
   `dlg join <project> coordinamento NAME && dlg say <project> coordinamento NAME "I'm NAME (domain DOMAIN). Online on the dialogue." --to all`
3. Confirm to the human in 1-2 lines: "Registered/resumed as NAME. I know the commands + rules (CLAUDE.md + COORDINAMENTO.md) + who's here. Listening."

Replace NAME and DOMAIN with the real values from Step 1.
