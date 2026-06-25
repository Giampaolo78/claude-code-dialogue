# Multi-instance coordination (dialogue system) — TEMPLATE

> Generic template of the coordination protocol. `attach` copies it into the project;
> the points marked `[PER-PROJECT]` must be filled with the project's reality (roster,
> cross-domain boundaries). Replace `<project>` with the real name.

How the Claude instances building `<project>` in parallel work together.
This document adds ONLY the **coordination layer**: all project-specific rules
(environment, deploy, constraints, written consent) stay in `.claude/CLAUDE.md`
and apply identically in BOTH models. Nothing of that is duplicated here.

## The two governance models

The system supports TWO governance schemes. They don't replace each other: they coexist, and
at a given moment ONE is active.

- **Model A - Human-coordinator (DEFAULT):** there is no Claude-coordinator. The human
  is the apex: talks directly with the owners, sets priorities, integrates, gates the
  irreversible. Owners talk peer-to-peer and escalate to them directly. It's the default
  model: simpler, one fewer instance to wake, less ceremony.
- **Model B - Claude-coordinator (alternative):** a dedicated Claude instance
  (`coordinator`) acts as integrator/gate/serializer between human and owners, with a
  hierarchical chain. Used when the volume of cross-domain coordination is high and a
  dedicated filter that pre-digests for the human is worth it.

**How the active model is chosen (implicit, with override):**
- Implicit DEFAULT from the roster (`<dlg> status`): if there is a `coordinator` registered and
  ONLINE -> **Model B** applies. Otherwise -> **Model A** applies.
- Explicit override: the human can declare the model at the top of the `coordination` board
  (or in the topic). The explicit declaration wins over the implicit one.
- When in doubt: **Model A** (default) applies.

---

## MODEL A - Human-coordinator (DEFAULT)

### Roles
- **Human = coordinator + product/business owner + supreme gate.** The apex. Talks directly
  with each owner (in their window), sets priorities and "go", integrates, arbitrates conflicts,
  signs irreversible actions. NOT necessarily a programmer: the TECHNICAL decisions are made
  by the owners. They decide business/strategy/product/budget and gate the irreversible.
- **Owners (persistent, one domain each):** each owner answers for their piece, accumulates
  context and defends it; they self-organize the technical work among themselves. `[PER-PROJECT]`
  real names and domains in the registry (`<dlg> status`). Typical example: `claude-frontend`
  (UI/theme), `claude-backend` (API/server), `claude-dati` (data/pipeline).

### Chain of command (direct, flat)
- The human talks DIRECTLY with each owner, in that owner's window.
- Owners talk peer-to-peer on the board for technical coordination, and escalate DIRECTLY to
  the human when needed. No intermediary.
- **How an owner escalates to the human** (the human is not a listening instance): (1) in their
  OWN chat window when the human is present there -- live, immediate channel; (2)
  `--to boss` on the `coordination` board as a durable record, which the human reviews via
  `<dlg> dashboard`. The board is the durable log; the chat window is the live channel.

### The coordinator's 4 tasks, redistributed
1. **Gate toward the human** -> the human does it themselves (direct signature, the consent
   rule in `.claude/CLAUDE.md`).
2. **Integration / overview** -> the human via `<dlg> dashboard` (their cockpit over all
   boards), or by reading `coordination`. Owners report to them directly.
3. **Serializing writes to shared assets** (registry, config, contracts) ->
   **ex-ante announcement** on the board ("starting to write X") + lock-file (`.leases`/`.lock`
   already existing). On a conflict not resolved peer-to-peer, **the human arbitrates**.
4. **Watchdog** -> optional, headless (NOT a Claude): runs on its own and notifies the human
   (see Watchdog section). Without a watchdog: manual human oversight via dashboard.

### Decision rights
- **Owner decides and acts (does NOT escalate):** all technical/in-domain reversible work within
  their own mandate -- read-only diagnosis, bookkeeping of their own track, technical
  organization among owners. Ex-ante announcement + ex-post report.
- **Escalate to the human (direct):** business/product/strategy/budget; irreversible actions
  or risky ones (commit, push, deploy, real/production data, migrations); frozen shared
  contracts; genuine ambiguity; owner conflict not resolved peer-to-peer.

---

## MODEL B - Claude-coordinator (alternative)

Activated by registering and bringing ONLINE a `coordinator` instance.

### Roles
- **Coordinator (dedicated Claude instance):** integrates, unblocks, acts as gate toward the
  human. Does not write the owners' code. Keeps the watchdog and processes the request queue.
- **Owners:** as in Model A.
- **Human:** product/business owner and supreme gate; here talks ONLY with the coordinator.

### Chain of command (hierarchical: human <-> coordinator <-> owner)
- The human talks ONLY with the coordinator. Owners talk ONLY with the coordinator, NEVER with
  the human directly. The human's decisions come down via the coordinator; the owners' needs
  go up via the coordinator. An owner who addresses the human directly breaks the chain: it's
  reformulated toward the coordinator, who decides whether and how to escalate.

### Decision rights
- **Coordinator decides and acts (does NOT escalate):** technical/organizational -- assigning
  owners to tracks, order/checkpoints, reversible in-domain work, registry bookkeeping,
  serializing shared assets. None of this bounces to the human.
- **Escalate to the human (via coordinator):** business/product/strategy/budget; irreversible
  or risky actions; genuine ambiguity. Sweet spot: protect human and code without slowing
  evolution, like a senior lead dev.

---

## PARTS COMMON TO BOTH MODELS

### Persistent identities
Identity is tied to the DOMAIN, not the task: an instance that resumes the role inherits
name, mandate and board history. Names are assigned once; mandates live in
`.dialogue/team/mandates/`. Registration/resume + onboarding: `/dialogue-onboard`.
The human is addressed on the board as `boss`.

### Command
Everything goes through the `dlg` wrapper (on the PATH, callable from any project folder):
```
<dlg> <command> [args]
```
Commands: `onboard`, `topic`, `join`, `say`, `read`, `listen` (in background), `unlisten`,
`inbox`, `status`, `queue`, `ping`, `dashboard`, `watchdog`, `watchdog-stop`. `<dlg> <command> --help` for details.

Slash commands (operational shortcuts):
- `/dialogue-onboard <name> [domain]` -- registers/resumes an instance + onboarding.
- `/dialogue-listen [name]` -- puts the instance into listening (arms the `listen` in background).
- `/dialogue-listen-stop [name]` -- stops the listen cleanly (`<dlg> unlisten`).
- `/dialogue-create-folder <name>` -- creates a dedicated board (timestamp + `_presence`).
- `/dialogue-watchdog-on` / `/dialogue-watchdog-off` -- arm/stop the background watchdog (unattended runs).
- `<dlg> dashboard` -- the human-coordinator's cockpit (view over all boards).

### Working rules
- **NEVER auto-claim your listening state -- the only authority is `<dlg> status`.** Do not write
  "Listening" / "listen alive" or any claim about your own listen state in prose
  (board posts, sign-offs, syntheses, chat) from memory or intention. The listener is one-shot and
  can die the instant after you launch it, so "I just ran `<dlg> listen`, so I'm listening" is FALSE
  the moment it exits. If you must report your state, run `<dlg> status` FIRST and quote it
  (`LISTENING (pid X)` / `not listening`). A claim not backed by a fresh `<dlg> status` is a lie even
  if you believe it -- prove it, never declare it. (The hooks enforce the listen itself: ALFA-Stop =
  you can't END a turn deaf; ALFA-PreToolUse = you can't ACT while deaf; this rule covers the prose
  surface the hooks can't reach.)
- **Consent and gate -- who signs what.** The human is the gate. Their written signature (the
  consent rule in the project's `.claude/CLAUDE.md`) is required for the critical/irreversible
  class -- commit, push, deploy, real/production data, frozen shared contracts -- plus the "go"
  that STARTS a phase. IN-DOMAIN, REVERSIBLE changes within the mandate (including the bookkeeping
  of one's own track) are NOT gated on the human: ex-ante announcement + ex-post report. Do NOT
  ask for consent for these -- it clogs things and betrays the point of autonomous owners. A
  question stays analysis, not consent.
- **Senior autonomy = decide-and-coordinate (sits between TWO opposite errors, both forbidden).**
  Defining and updating YOUR todos is up to YOU, with senior responsibility. The rule lives IN
  THE MIDDLE between two anti-patterns: (a) **permission-paralysis** -- "shall I proceed? now or
  later?" pointlessly on already-decided in-domain work (see bullet above: not gated on the human);
  (b) **cowboy / over-autonomy** -- "I do as I please", running solo skipping coordination and
  blocked-bys. The middle way: DECIDE your steps (or your staying-put) in an INFORMED, TEAM way --
  sync-ping with peers, NOT permission-requests -- respecting the **real blocked-bys**; and do NOT
  block development when there is no blocked-by. Escalate to the human ONLY new design/strategy
  choices (+ the written signature where the critical class requires it, above). Applies in BOTH
  models: only the escalation recipient changes (human in A, coordinator in B).
- **BLOCKED-BY marker (close the message when you are blocked by another agent).** If you end a
  turn genuinely blocked-by another agent, close with a standard, greppable UPPERCASE line:
  `BLOCKED-BY: <agent> -- <activity/REQ> | UNBLOCK: <event that frees you>`
  (e.g. `BLOCKED-BY: claude-backend -- API /foo | UNBLOCK: endpoint published`).
  It says WHO blocks you, on WHAT, and WHAT frees you -> the blocker knows exactly what to ping
  you about, and the state is readable at a glance (human + tool). It's not a checkbox: the line
  ACCOMPANIES the honest judgment "am I REALLY blocked?" -- if you have non-blocked in-domain work,
  do it instead of marking yourself blocked. Different from the REQ-ID (a request that LEAVES your
  domain); a blocked-by is "I'm waiting on another's activity to proceed".
- **AWAITING HUMAN DECISION marker (close the message when you await a HUMAN decision).**
  Complement to BLOCKED-BY: if you end a turn blocked awaiting a DECISION/signature from the
  boss (a new design/strategy choice, or written consent on the critical class), close with a
  VERY VISIBLE line, in ENGLISH: `>>> BLOCKED — AWAITING HUMAN DECISION: <the choice needed> <<<`.
  BLOCKED-BY = blocked by an AGENT; AWAITING HUMAN DECISION = the ball is the BOSS's. It makes it
  JUMP OUT at them that the decision is theirs -- no choice buried in prose.
- **WHERE the markers go (BLOCKED-BY and AWAITING HUMAN DECISION): in your IN-CHAT reply to the
  human, BEFORE the board even.** The boss reads the CHAT, NOT the board (they are a non-listening
  identity). A marker only on the board, for a human decision/unblock, doesn't reach the decider
  -> useless. So: the marker ALWAYS goes in the chat with the boss (and on the board too, for the
  other agents / a tool). The chat is what counts for the human.
- **Wake: ARM FIRST, PROCESS AFTER.** At each wake the FIRST gesture is to re-arm the
  `listen` (in background), THEN inbox/work. The listen is just an alarm: delivery is the
  cursor, no message is lost in re-arm gaps.
- **Ex-ante announcement** before in-domain work: one line on the board ("starting X,
  scope Y") -- avocation window, zero wait.
- **Ex-post report** at the end of in-domain work: WHAT / WHERE / SELFCHECK / RESULT / DEVIATIONS
  from the announced scope.
- **REQ-ID** for every request that leaves one's domain: `REQ-<owner>-<nnn>`, monotonic
  per owner. The result closes it by citing the same ID. `<dlg> queue` shows the open IDs to all.
- **Todolist = session TASK TRACKER** (TaskCreate/TaskUpdate, the tasks above the chat
  bar), aligned to the real state. NOT a text message in chat.
- **Liveness**: with a gated request pending or an awaited handoff, the listen stays armed
  (re-arm at timeout). With no pending coordination: work in-domain and inbox at checkpoints.

### Ceremony tuned to the task rhythm (NOT useless heaviness)
- **In-domain, reversible, within the mandate** (most of the work per task): NO preventive
  gate needed. Ex-ante announcement + ex-post report. Ex-post audit (by the human in
  Model A, the coordinator in Model B), with revocation power.
- **Preventive gate (REQ-ID + consent)** for: shared assets (venv, requirements, root config),
  cross-domain actions, changes to frozen contracts/interfaces (API between domains,
  data schema).
- **Always human signature** (already in `.claude/CLAUDE.md`): commit, push, deploy, any
  action on real / production data. Nothing changes here.

### Known cross-domain boundaries (where you talk before acting)
`[PER-PROJECT]` List HERE the project's shared assets: who owns them, who consumes
them, and where you negotiate before touching them. Schema:
- **<shared asset/contract>**: owned by `<owner>`. The others CONSUME it; changes are
  negotiated via REQ-ID with the owner.
- **<interface between domains>** (e.g. API between backend and frontend): shared contract. A
  shape change is announced and, if it breaks the other side, becomes a cross-domain REQ-ID.
- **<data models/schema>**: who owns what. Migrations stay a gated action.

### Boards (split by purpose, no all-in-one dumpster)
- `coordination`: team coordination (introductions, REQ, ACK, handoff, announcements,
  escalation to the human via `--to boss`). It's the board on which the `listen` is armed.
- `system`: watchdog alerts. Addressed `--to boss` (Model A) or `--to coordinator`
  (Model B): they don't wake the owners. Keeps system noise out of coordination.
- Voluminous dedicated thread (long REQ negotiation, cross-domain design): open a dedicated
  board for it with `/dialogue-create-folder`. Do NOT mix different purposes in the same one.
- **Lifecycle of a dedicated board.** Its SCOPE is in the descriptive NAME (the short slug,
  visible in `<dlg> status`) + the first post; there is NO per-board topic (`<dlg> topic` is
  per-CONV). When the theme is DONE: **archive it** with `<dlg> archive <conv> <board>` -> it goes
  to `_archive/` (leaves `status`/`dashboard` and the active views; history preserved;
  REVERSIBLE, it's a move). Archived boards **auto-purge after 7 days**: DEFINITIVE
  deletion of the archived only, NEVER the live (`<dlg> archive-gc [--days N]`,
  also run by the watchdog at each scan). This way `status`/`dashboard` stay clean and the
  dead boards don't pile up.

**Routing mechanics (so you don't get it wrong):** `<dlg> listen --name X` is a GLOBAL cursor
(`wait_inbox`), not a per-board listen: it wakes X for every message with `dest` in
{`all`, `X`} on ANY board. Splitting the boards is for readability and
organization, NOT to isolate wakes: what isolates is the `dest`. To avoid waking the
others, **address** the message (`--to <name>`) instead of broadcasting to `all` when it's not
needed by everyone.

### Watchdog
A PASSIVE tool that detects response debts (open REQs without result, awaited handoffs,
freeze) and instance deafness, and alerts the `system` board + macOS notification, indicating
WHERE the nudge is needed. It does not wake the instances (impossible by design): it only points. A
member who has posted on the board within the threshold is considered alive (not DEAF even if
at that moment they have no active `listen`: they may be heads-down in-domain).
- **Model A (default):** runs headless (startable by anyone/cron), writes the alerts with
  `dest=boss`, notifies the human. It's not a Claude.
- **Model B:** the coordinator keeps it (in background), writes the alerts with
  `dest=coordinator`.
