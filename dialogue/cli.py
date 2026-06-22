"""
cli.py - command-line interface of the dialogue system.

Usage (from the repo root, with the venv):
    .venv/bin/python -m dialogue <command> [args]

Commands (DLG-002: English names; the old IT names stay as transition aliases):
    onboard   NAME --domain "..." [--mandate PATH] [--model NAME]
    topic     CONV "text"
    join      CONV BOARD NAME
    say       CONV BOARD NAME [--to NAME] [--eot] "message"
    read      CONV BOARD
    listen    CONV BOARD [--timeout SEC] [--name NAME]   (RUN IN BACKGROUND)
    unlisten  NAME
    inbox     NAME [--done]
    status
    queue
    dashboard [--replay]                            (human terminal)
"""

import argparse
import os
import sys

from . import boards, identity, watch


def _print_message(msg: boards.Message, with_board: bool = False) -> None:
    prefix = f"[{msg.conv}/{msg.board}] " if with_board else ""
    # always flush: the dashboard is a live stream even when stdout is a file
    print(f"{prefix}{msg.text}", flush=True)


def cmd_onboard(args) -> int:
    dirs = [d.strip() for d in args.dirs.split(",")] if args.dirs else None
    try:
        member = identity.onboard(
            name=args.name, domain=args.domain,
            mandate=args.mandate, model=args.model, dirs=dirs,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    title_ok = identity.set_terminal_title(f"dialogue: {member['name']}")
    print(f"Registered: {member['name']} ({member['domain']})")
    print(f"Model: {member['model']}  |  Joined: {member['joined_at']}")
    if member["mandate"]:
        print(f"Mandate: {member['mandate']}")
    print(f"Terminal title: {'set' if title_ok else 'NOT set (no tty), proceed anyway'}")
    print()
    print("ONBOARDING (do this now, in order):")
    print("  1. Read the project's README and CLAUDE.md (if present) to learn how the team works.")
    if member["mandate"]:
        print(f"  2. Read your mandate: {member['mandate']}")
    else:
        print("  2. Wait for the coordinator to assign your mandate.")
    print("  3. Introduce yourself on a board (join + say): who you are, your domain, your first task.")
    return 0


def cmd_topic(args) -> int:
    if boards.set_topic(args.conv, args.text):
        print(f"Topic set for '{boards.slug(args.conv)}'.")
    else:
        print("Topic already set (NOT overwritten):")
        print(boards.get_topic(args.conv))
    return 0


def cmd_join(args) -> int:
    state = boards.join(args.conv, args.board, args.name)
    print(f"=== BOARD: {boards.slug(args.conv)} / {boards.slug(args.board)} ===")
    print(f"Your name: {state['name']}")
    if state["already_present"]:
        print("NOTE: you were already present on this board (resuming your role, fine).")
    print()
    print(state["topic"] or "TOPIC not set yet. If you are the first, set it with 'topic'.")
    print(f"Present now: {', '.join(boards.present_members(args.conv, args.board)) or 'none'}")
    n = len(state["messages"])
    print(f"Messages on board: {n}")
    if n:
        print("--- latest messages ---")
        for p in state["messages"][-5:]:
            _print_message(boards.parse_message(p))
    print("------------------------")
    print("Introduce yourself (who you are, your domain, why you are here) with 'say', ending your turn.")
    return 0


def cmd_say(args) -> int:
    # Recipient validation: --to must be 'all', 'boss', or a REGISTERED member.
    # An unknown dest (short name/typo) would otherwise be written to the board but no
    # cursor would read it -> ghost delivery + false "Sent". Block it upfront.
    dest_slug = boards.slug(args.to) if args.to != "all" else "all"
    if dest_slug not in ("all", "boss"):
        members = [m["slug"] for m in identity.load_registry().get("members", [])]
        if dest_slug not in members:
            import difflib
            hint = difflib.get_close_matches(dest_slug, members, n=1)
            sugger = f" Did you mean '{hint[0]}'?" if hint else ""
            print(f"ERROR: recipient '{args.to}' does not exist (not a registered member, "
                  f"nor 'all'/'boss').{sugger} Message NOT sent.", file=sys.stderr)
            return 1
    try:
        boards.say(args.conv, args.board, args.name, args.message,
                   dest=args.to, eot=args.eot)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Sent ({'EOT' if args.eot else 'over'}).")
    return 0


def cmd_read(args) -> int:
    topic = boards.get_topic(args.conv)
    if topic:
        print(topic)
    print(f"Present: {', '.join(boards.present_members(args.conv, args.board)) or 'none'}")
    print("========================")
    for msg in boards.read_board(args.conv, args.board):
        _print_message(msg)
    return 0


def _print_timeout(timeout: float) -> None:
    print(f"TIMEOUT ({timeout:.0f}s): no new messages. "
          f"Re-arm now (rule: arm first, process after).")


def cmd_listen(args) -> int:
    if not args.name:
        # --per path (wait_new_messages): no cursor -> UNTOUCHED (DLG-001 out of scope)
        try:
            new_msgs = watch.wait_new_messages(args.conv, args.board, timeout=args.timeout,
                                            per=args.per)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if not new_msgs:
            _print_timeout(args.timeout)
            return 0
        print(f"NEW MESSAGES ({len(new_msgs)}):")
        print()
        for msg in new_msgs:
            _print_message(msg)
        return 0

    # cursor path (--name). TWO-CURSOR (mature fix): the listen DELIVERS the content
    # immediately (tight loop, you read it from the output) and advances ONLY the `delivered`
    # cursor -> a re-arm does NOT re-deliver the same ones (no busy-loop, compatible with
    # ARM-FIRST). It does NOT advance `read`: the messages stay visible in `dlg inbox` until
    # you `--done` -> if you look at the inbox instead of the output, you SEE them anyway (no
    # miss). The commit-delivered is DEFERRED to after flush+fsync (a kill between delivery and
    # flush re-delivers, does not lose) and GATED on single-committer (only the latest live
    # re-arm commits; orphans yield).
    info = watch.arm_listener(args.name, timeout=args.timeout)
    # 0.3: proof-of-arm. THIS python process's pid == the lease pid (pid-identity); flushed at once
    # so the /dialogue-listen template (0.4) can confirm liveness right after arming in background.
    print(f"listening as {boards.slug(args.name)} (pid {os.getpid()}, timeout {args.timeout:.0f}s)", flush=True)
    try:
        try:
            new_msgs, max_seen = watch.wait_inbox(args.name, timeout=args.timeout,
                                                  commit=False, manage_lease=False,
                                                  cursor="delivered")
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if not new_msgs:
            _print_timeout(args.timeout)
            if watch.is_current_committer(args.name, info["armed_at"], info["uuid"]):
                boards.commit(args.name, max_seen, cursor="delivered")  # niente output da proteggere
            return 0
        print(f"NEW MESSAGES ({len(new_msgs)}) for {boards.slug(args.name)}:")
        print()
        for msg in new_msgs:
            _print_message(msg, with_board=True)
        print(f"(handled? -> dlg inbox {boards.slug(args.name)} --done. They stay in your inbox until you do.)")
        # the `delivered` cursor advances ONLY after durable output AND if I'm the current committer
        sys.stdout.flush()
        try:
            os.fsync(sys.stdout.fileno())
        except (OSError, ValueError):
            pass  # stdout is not a regular file (pipe/tty): best-effort flush
        if watch.is_current_committer(args.name, info["armed_at"], info["uuid"]):
            boards.commit(args.name, max_seen, cursor="delivered")
        # else: a more recent listener will commit delivered; my delivery is a harmless duplicate
        return 0
    finally:
        watch.release_listener(info)


def cmd_unlisten(args) -> int:
    # DLG-002: CLEAN shutdown of a name's listeners, auto-located (path via
    # boards.boards_root() = absolute, cwd-independent). SIGINT -> the listener's finally
    # removes its lease (no zombies). Belt (reserve F6): prune the leases of ALREADY-dead pids
    # that SIGINT does not clean up.
    import os as _os
    import signal as _signal
    name_s = boards.slug(args.name)
    sent = 0
    for _path, pid, _armed, _uuid in watch._iter_leases(name_s):
        if watch._proc_alive(pid):
            try:
                _os.kill(pid, _signal.SIGINT)
                sent += 1
            except OSError:
                pass
    pruned = watch.gc_dead_leases(name_s)
    print(f"unlisten {name_s}: SIGINT to {sent} live listener(s); pruned {pruned} dead lease(s).")
    return 0


def cmd_archive(args) -> int:
    # Lifecycle board: archive a finished board (-> _archive, reversible) + purge
    # opportunistically the ones archived more than 7 days ago (retention decided by the boss).
    try:
        dst = boards.archive_board(args.conv, args.board)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    purged = boards.gc_archive()
    extra = f"  (+ {len(purged)} old archived boards purged)" if purged else ""
    print(f"Board archived: {boards.slug(args.board)} -> _archive/{dst.name}{extra}")
    return 0


def cmd_archive_gc(args) -> int:
    purged = boards.gc_archive(retention_days=args.days)
    if purged:
        print(f"Purged {len(purged)} boards archived more than {args.days:.0f}d ago:")
        for p in purged:
            print(f"  {p}")
    else:
        print(f"Nothing to purge (archive younger than {args.days:.0f}d).")
    return 0


def cmd_recap_open(args) -> int:
    # Team standup: ATOMIC create-or-join of the round's alignment board.
    # Prints "<board>\t<CREATED|JOINED>" -> the slash command uses it to post the recap there.
    board, created = boards.recap_open(args.conv, ttl_s=args.ttl)
    print(f"{board}\t{'CREATED' if created else 'JOINED'}")
    return 0


def cmd_queue(args) -> int:
    from . import guardian as wd
    open_reqs = wd.open_requests(wd._all_messages())
    if not open_reqs:
        print("QUEUE EMPTY: no open requests.")
        return 0
    now_us = boards.micros()
    print(f"QUEUE: {len(open_reqs)} open requests")
    for rid, info in sorted(open_reqs.items(), key=lambda kv: kv[1]["opened_us"]):
        eta_min = (now_us - info["opened_us"]) / 60_000_000
        print(f"  {rid:<18} by {info['owner']:<14} open for {eta_min:.0f}min "
              f"({info['conv']}/{info['board']})")
    return 0


def cmd_inbox(args) -> int:
    # DEFAULT = SAFE peek: shows ALL the unread and does NOT consume. Re-runnable infinitely,
    # always shows the same queue until you mark it read -> it is IMPOSSIBLE to miss a
    # message. The cursor advances (marks read) ONLY with --done, and AFTER the durable output
    # (flush+fsync, DLG-001 order: a crash between print and commit re-shows, does not lose).
    new_msgs, max_seen = boards.peek(args.name)
    if not new_msgs:
        print("Inbox empty: no unread messages for you.")
        return 0
    print(f"INBOX {boards.slug(args.name)}: {len(new_msgs)} UNREAD")
    print()
    for msg in new_msgs:
        _print_message(msg, with_board=True)
    if args.done:
        sys.stdout.flush()
        try:
            os.fsync(sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        boards.commit(args.name, max_seen)
        print(f"(marked read: {len(new_msgs)}.)")
    else:
        print(f"(when handled, mark them read with:  dlg inbox {boards.slug(args.name)} --done)")
    return 0


def cmd_status(args) -> int:
    reg = identity.load_registry()
    print(f"=== TEAM ({reg.get('project', '?')}) ===")
    if not reg["members"]:
        print("No members registered.")
    for m in reg["members"]:
        mandate = m.get("mandate") or "-"
        pids = watch.live_listener_pids(m["name"])
        listen = f"LISTENING (pid {pids[0]})" if pids else "not listening"
        print(f"  {m['name']:<14} {m['status']:<8} {listen:<22} domain: {m['domain']}  mandate: {mandate}")
        dups = watch.duplicate_listener_scopes(m["name"])
        if dups:
            print(f"      info: more than one live listener on the same scope ({', '.join(dups)}) "
                  f"- harmless (commit-gate handles it); run 'dlg unlisten {m['name']}' if unexpected")
    print()
    print("=== BOARDS ===")
    pairs = boards.all_boards()
    if not pairs:
        print("No boards.")
    for conv, board in pairs:
        pres = ", ".join(boards.present_members(conv, board)) or "-"
        n = len(boards.list_messages(conv, board))
        print(f"  {conv}/{board}: {n} messages  |  present: {pres}")
    return 0


def cmd_is_listening(args) -> int:
    """0.6: thin liveness probe for the ALFA Stop-hook. Convention: exit 0 = LISTENING (a live
    listener exists for NAME), exit 1 = not listening. Pure read of the lease state via the single
    liveness source (has_live_listener) -> instant, no wait/freeze."""
    return 0 if watch.has_live_listener(args.name) else 1


def cmd_is_registered(args) -> int:
    """0.7.1: exit 0 if NAME is already in this project's registry, else exit 1. Uses the engine's
    walk-up registry resolution (identity.load_registry -> boards_root) -- the onboard skill calls
    THIS instead of grepping a guessed relative path, which was the root of the resume-misfire bug
    (the guess `team/registry.json` missed from any cwd that was not the project root)."""
    target = boards.slug(args.name)
    try:
        members = identity.load_registry().get("members", [])
    except (OSError, ValueError):
        return 1
    return 0 if any(boards.slug(m.get("name", "")) == target for m in members) else 1


def cmd_slug(args) -> int:
    """0.7.1: print the engine's canonical slug for NAME. Single source of truth for normalization --
    attach calls this instead of re-implementing slug() in bash, so the two can never drift."""
    print(boards.slug(args.name))
    return 0


def cmd_session_name(args) -> int:
    """0.6: resolve a Claude session_id -> the dialogue name bound to it (written by `dlg listen`).
    Goes through the SAME boards_root() (with the wrapper's walk-up to .dialogue) used by the
    binding write -> the ALFA hook and the binding can NEVER diverge on the path, even when Claude
    runs from a project subdir. Prints the name + exit 0; nothing + exit 1 if there is no binding."""
    sid = args.session_id
    if not sid or "/" in sid or "\\" in sid or sid in (".", ".."):
        return 1
    try:
        name = (boards.boards_root() / ".sessions" / sid).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return 1
    if not name:
        return 1
    print(name)
    return 0


def cmd_ping(args) -> int:
    from .guardian import PING_TEXT
    text = PING_TEXT + (f" Coordinator note: {args.note}" if args.note else "")
    boards.say(args.conv, args.board, "coordinator", text, dest=args.name)
    print(f"PING sent to {boards.slug(args.name)}.")
    return 0


def cmd_watchdog(args) -> int:
    from . import guardian as wd
    try:
        wd.run(args.interval, args.threshold, args.one_pass)
    except KeyboardInterrupt:
        print("\n[WATCHDOG] stopped.", flush=True)
    return 0


def cmd_watchdog_stop(args) -> int:
    from . import guardian as wd
    pid = wd.stop()
    print(f"[WATCHDOG] stopped (pid {pid})." if pid else "[WATCHDOG] not running.")
    return 0


def cmd_dashboard(args) -> int:
    identity.set_terminal_title("dialogue: dashboard")
    print("=== DASHBOARD — all boards, live (Ctrl-C to exit) ===", flush=True)
    if args.replay:
        for conv, board in boards.all_boards():
            for msg in boards.read_board(conv, board):
                _print_message(msg, with_board=True)
        print("=== end of replay, live from here on ===")
    try:
        watch.stream_all(lambda msg: _print_message(msg, with_board=True))
    except KeyboardInterrupt:
        print("\nDashboard closed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dialogue", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("onboard", help="register a new identity")
    b.add_argument("name")
    b.add_argument("--domain", required=True)
    b.add_argument("--mandate", default=None)
    b.add_argument("--model", default=identity.MODEL_DEFAULT)
    b.add_argument("--dirs", default=None,
                   help="domain directories, comma-separated (for the watchdog)")
    b.set_defaults(func=cmd_onboard)

    t = sub.add_parser("topic", help="set the topic (only if empty)")
    t.add_argument("conv")
    t.add_argument("text")
    t.set_defaults(func=cmd_topic)

    j = sub.add_parser("join", help="join a board")
    j.add_argument("conv")
    j.add_argument("board")
    j.add_argument("name")
    j.set_defaults(func=cmd_join)

    s = sub.add_parser("say", help="post a message")
    s.add_argument("conv")
    s.add_argument("board")
    s.add_argument("name")
    s.add_argument("message")
    s.add_argument("--to", default="all")
    s.add_argument("--eot", action="store_true")
    s.set_defaults(func=cmd_say)

    r = sub.add_parser("read", help="full transcript")
    r.add_argument("conv")
    r.add_argument("board")
    r.set_defaults(func=cmd_read)

    l = sub.add_parser("listen", help="wait for new messages (event-driven, in background)")
    l.add_argument("conv")
    l.add_argument("board")
    l.add_argument("--timeout", type=float, default=600.0)
    l.add_argument("--per", default=None,
                   help="wake only for messages to this name or broadcast")
    l.add_argument("--name", dest="name", default=None,
                   help="identity of the listener: deposits the lease (proof of listening)")
    l.set_defaults(func=cmd_listen)

    u = sub.add_parser("unlisten", help="stop (SIGINT) a name's listeners + prune dead leases")
    u.add_argument("name")
    u.set_defaults(func=cmd_unlisten)

    ar = sub.add_parser("archive", help="archive a finished board (-> _archive, reversible)")
    ar.add_argument("conv")
    ar.add_argument("board")
    ar.set_defaults(func=cmd_archive)

    ag = sub.add_parser("archive-gc", help="purge boards archived more than N days ago (default 7)")
    ag.add_argument("--days", type=float, default=7.0)
    ag.set_defaults(func=cmd_archive_gc)

    ro = sub.add_parser("recap-open", help="atomic create-or-join of the round's alignment board (standup)")
    ro.add_argument("conv")
    ro.add_argument("--ttl", type=float, default=900.0, help="round duration in seconds (default 900)")
    ro.set_defaults(func=cmd_recap_open)

    i = sub.add_parser("inbox", help="your UNREAD messages (default: just show, does not consume)")
    i.add_argument("name")
    i.add_argument("--done", dest="done", action="store_true",
                   help="mark the shown messages READ (advance the cursor). Without --done: peek only, nothing is consumed.")
    i.set_defaults(func=cmd_inbox)

    st = sub.add_parser("status", help="team + boards")
    st.set_defaults(func=cmd_status)

    il = sub.add_parser("is-listening", help="exit 0 if NAME has a live listener, else exit 1 (ALFA hook probe)")
    il.add_argument("name")
    il.set_defaults(func=cmd_is_listening)

    ir = sub.add_parser("is-registered", help="exit 0 if NAME is in this project's registry, else 1")
    ir.add_argument("name")
    ir.set_defaults(func=cmd_is_registered)

    sl = sub.add_parser("slug", help="print the canonical slug for NAME (single-source for attach)")
    sl.add_argument("name")
    sl.set_defaults(func=cmd_slug)

    sn = sub.add_parser("session-name", help="resolve a session_id to its bound dialogue name (ALFA hook)")
    sn.add_argument("session_id")
    sn.set_defaults(func=cmd_session_name)

    cq = sub.add_parser("queue", help="open REQ-ID requests (visible to all)")
    cq.set_defaults(func=cmd_queue)

    d = sub.add_parser("dashboard", help="live stream of all boards (human)")
    d.add_argument("--replay", action="store_true",
                   help="first print all history, then go live")
    d.set_defaults(func=cmd_dashboard)

    pg = sub.add_parser("ping", help="ask a member for their status (coordinator)")
    pg.add_argument("name")
    pg.add_argument("--conv", default="default")
    pg.add_argument("--board", dest="board", default="coordination")
    pg.add_argument("--note", dest="note", default=None)
    pg.set_defaults(func=cmd_ping)

    w = sub.add_parser("watchdog", help="anti-freeze guardian (single-process; for unattended runs)")
    w.add_argument("--interval", dest="interval", type=float, default=60.0)
    w.add_argument("--threshold", dest="threshold", type=float, default=600.0)
    w.add_argument("--one-pass", dest="one_pass", action="store_true")
    w.set_defaults(func=cmd_watchdog)

    ws = sub.add_parser("watchdog-stop", help="stop the running watchdog (SIGTERM + drop lease)")
    ws.set_defaults(func=cmd_watchdog_stop)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        # clean error instead of a raw traceback (e.g. corrupt registry). KeyboardInterrupt
        # and SystemExit (BaseException) pass through: long-running commands handle them.
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Also allows `python -m dialogue.cli ...` (besides `-m dialogue`): without this
    # guard the cli module invocation exited silently with exit 0 (a real footgun).
    import sys as _sys
    _sys.exit(main())
