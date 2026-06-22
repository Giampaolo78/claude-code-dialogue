"""
selfcheck.py - end-to-end check of the dialogue system in a sandbox.

Runs the checks in a temporary directory (override via env DIALOGUE_BOARDS_ROOT
and DIALOGUE_TEAM_ROOT): it touches neither the real boards nor the real registry.

Usage:  .venv/bin/python -m dialogue.selfcheck

NB: no pytest and no test_-prefixed functions (project rule).
"""

import os
import sys
import tempfile
import threading
import time

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    state = "OK  " if ok else "FAIL"
    print(f"[{state}] {name}" + (f" - {detail}" if detail else ""))


def check_storage(boards) -> None:
    first = boards.set_topic("conv1", "test topic")
    second = boards.set_topic("conv1", "overwrite attempt")
    record("atomic topic (first wins)", first is True and second is False)

    boards.join("conv1", "board1", "alfa")
    boards.join("conv1", "board1", "beta")
    record("join + presence", boards.present_members("conv1", "board1") == ["alfa", "beta"])

    boards.say("conv1", "board1", "alfa", "first test message")
    boards.say("conv1", "board1", "beta", "test reply", dest="alfa")
    msgs = boards.read_board("conv1", "board1")
    record("write + ordered read", len(msgs) == 2 and msgs[0].author == "alfa")
    record("recipient in the header", msgs[1].dest == "alfa")

    boards.say("conv1", "board1", "beta", "closing", eot=True)
    record("EOT removes the presence", boards.present_members("conv1", "board1") == ["alfa"])

    expected_error = False
    try:
        boards.say("conv1", "nonexistent-board", "alfa", "x")
    except FileNotFoundError:
        expected_error = True
    record("say on a nonexistent board -> error", expected_error)


def check_watch_event_driven(boards, watch) -> None:
    boards.join("conv1", "live", "alfa")

    result: dict = {}

    def listener():
        t0 = time.monotonic()
        msgs = watch.wait_new_messages("conv1", "live", timeout=10.0)
        result["msgs"] = msgs
        result["waited"] = time.monotonic() - t0

    th = threading.Thread(target=listener)
    th.start()
    time.sleep(0.5)  # the observer must be up
    boards.say("conv1", "live", "beta", "wake up!")
    th.join(timeout=12)

    msgs = result.get("msgs", [])
    waiting = result.get("waited", 999)
    record("event-driven listen receives the message",
             len(msgs) == 1 and msgs[0].author == "beta",
             f"waited {waiting:.2f}s")
    record("fast wake (event, not poll)", waiting < 3.0, f"{waiting:.2f}s")

    t0 = time.monotonic()
    empty_ones = watch.wait_new_messages("conv1", "live", timeout=1.0)
    duration = time.monotonic() - t0
    record("clean timeout with no messages", empty_ones == [] and 0.9 <= duration < 3.0,
             f"{duration:.2f}s")


def check_race_pre_observer(boards, watch) -> None:
    """A message that arrives BEFORE the observer starts: must not be lost."""
    boards.join("conv1", "race", "alfa")

    result: dict = {}

    def immediate_writer():
        boards.say("conv1", "race", "beta", "arrived immediately")

    th_w = threading.Thread(target=immediate_writer)

    def listener():
        result["msgs"] = watch.wait_new_messages("conv1", "race", timeout=5.0)

    th_l = threading.Thread(target=listener)
    th_l.start()
    th_w.start()
    th_w.join()
    th_l.join(timeout=7)
    record("snapshot/observer race handled", len(result.get("msgs", [])) == 1)


def check_identity(identity) -> None:
    m = identity.onboard("Test-One", domain="test domain")
    record("registration records", m["slug"] == "test-one" and m["status"] == "active")

    collision = False
    try:
        identity.onboard("test_one", domain="other")  # identical slug
    except ValueError:
        collision = True
    record("name collision prevented", collision)

    reg = identity.load_registry()
    record("registry persists", identity.find_member(reg, "Test-One") is not None)


def check_inbox(boards) -> None:
    boards.join("conv2", "work", "gamma")
    # baseline: the inbox is GLOBAL (all boards); the first pass absorbs the
    # history of the previous checks and pins gamma's checkpoint to "now"
    boards.inbox("gamma")
    boards.say("conv2", "work", "alfa", "message for everyone")
    boards.say("conv2", "work", "beta", "private message", dest="gamma")
    boards.say("conv2", "work", "beta", "not for gamma", dest="alfa")
    boards.say("conv2", "work", "gamma", "written by gamma itself")

    new_msgs = boards.inbox("gamma")
    authors = [m.author for m in new_msgs]
    record("inbox filters dest and author",
             len(new_msgs) == 2 and authors == ["alfa", "beta"],
             f"received: {authors}")

    again = boards.inbox("gamma")
    record("checkpoint advances (empty inbox on the second pass)", again == [])

    boards.say("conv2", "work", "alfa", "new after the checkpoint")
    third = boards.inbox("gamma")
    record("inbox resumes from the checkpoint", len(third) == 1)


def check_gap_recovery_cursor(boards, watch) -> None:
    """Point E of protocol v2: a message written WHILE NO listen is armed
    -> the next listen (single cursor) delivers it at startup, immediately."""
    boards.join("v2", "gap", "alfa")
    boards.inbox("gamma2")  # cursor baseline
    boards.say("v2", "gap", "alfa", "written in the gap, no one listening")

    t0 = time.monotonic()
    msgs, _ = watch.wait_inbox("gamma2", timeout=5.0)
    duration = time.monotonic() - t0
    record("gap-recovery: the cursor delivers at listen startup",
             len(msgs) == 1 and "written in the gap" in msgs[0].text and duration < 1.0,
             f"delivered in {duration:.2f}s")


def check_to_guaranteed(boards, watch) -> None:
    """Point F: a --to always reaches the recipient via the cursor."""
    boards.inbox("delta")  # baseline
    boards.say("v2", "gap", "alfa", "targeted message", dest="delta")
    boards.say("v2", "gap", "alfa", "message for others", dest="epsilon")
    msgs, _ = watch.wait_inbox("delta", timeout=5.0)
    record("--to guaranteed to the recipient (and only theirs)",
             len(msgs) == 1 and msgs[0].dest == "delta")


def check_concurrent_onboards(identity) -> None:
    """Point G: two simultaneous registrations, no lost-update (the 2026-06-10 race)."""
    results = {}

    def onboard(name):
        try:
            identity.onboard(name, domain=f"domain {name}")
            results[name] = True
        except ValueError:
            results[name] = False

    th = [threading.Thread(target=onboard, args=(f"conc-{i}",)) for i in range(4)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    reg = identity.load_registry()
    present_members = [m["slug"] for m in reg["members"] if m["slug"].startswith("conc")]
    record("concurrent registrations without loss (lock)",
             len(present_members) == 4 and all(results.values()),
             f"registered {len(present_members)}/4")

    journal = (identity.team_root() / "registry_journal.jsonl")
    lines = journal.read_text().strip().split("\n") if journal.is_file() else []
    record("append-only journal traces every registration", len(lines) >= 4)


def check_lease_multi_listen(boards, watch, watchdog) -> None:
    """claude-ml case (false DEAF, 2026-06-10): two parallel listens same name;
    the first to exit must NOT erase the other's listening-proof."""
    boards.join("v2", "multi", "omega")

    long_t: dict = {}

    def long_listener():
        long_t["msgs"] = watch.wait_new_messages("v2", "multi", timeout=6.0, name="omega")

    th = threading.Thread(target=long_listener)
    th.start()
    time.sleep(0.5)  # the long listener is up, lease deposited

    # second listen same name, exits immediately on timeout (was the lease killer)
    watch.wait_new_messages("v2", "multi", timeout=0.5, name="omega")

    still_alive = watchdog._lease_valid("omega")
    record("multi-listen lease: one exiting does NOT erase the other", still_alive)

    boards.say("v2", "multi", "alfa", "wake the long listener")
    th.join(timeout=8)
    after = watchdog._lease_valid("omega")
    record("lease removed only when the LAST listen exits", not after)


def check_liveness_and_alfa(boards, watch) -> None:
    """0.5 (PLAN F0): regression cover for the liveness layer (0.1/0.2/0.3/0.6) + the
    _proc_alive pid<=0 guard (worker2 anticorpo) + the ALFA session->name binding.
    DETERMINISTIC: controlled pids (this process = alive, a reaped subprocess = dead),
    NO sleep/timing, OS-agnostic. Covers LIVE-PID / DEAD / MISSING-PID / DUPLICATE / SESSION-NAME."""
    import json as _json
    import subprocess as _sp

    leases = boards.boards_root() / ".leases"
    leases.mkdir(parents=True, exist_ok=True)
    alive_pid = os.getpid()                                   # this process: alive by definition
    _d = _sp.Popen([sys.executable, "-c", "pass"]); _d.wait()
    dead_pid = _d.pid                                         # reaped -> reliably dead

    def write_lease(name, pid, tag, conv="*", board="*", with_pid=True):
        s = boards.slug(name)
        meta = {"conv": conv, "board": board, "armed_at": 1.0, "timeout": 0.0, "expires_at": 1.0}
        if with_pid:
            meta["pid"] = pid
        boards._atomic_write(leases / f"{s}.{pid}.{tag}.json", _json.dumps(meta))

    # LIVE-PID: a live lease reads as LISTENING and surfaces the (python) pid -> pid-identity.
    write_lease("liv-alive", alive_pid, "a")
    pids = watch.live_listener_pids("liv-alive")
    record("0.5 live: live-pid lease -> LISTENING + exact pid",
             watch.has_live_listener("liv-alive") and pids == [alive_pid], f"pids={pids}")

    # DEAD: a dead-pid lease -> not listening, and gc prunes it.
    write_lease("liv-dead", dead_pid, "a")
    pruned = watch.gc_dead_leases("liv-dead")
    record("0.5 dead: dead-pid lease -> not listening + gc'd",
             not watch.has_live_listener("liv-dead") and pruned >= 1)

    # MISSING-PID (worker2 bug): no 'pid' field -> defaults to -1; os.kill(-1,0) used to read
    # 'alive' (signal to ALL the user's procs) -> immortal 'pid -1' phantom. The guard makes it DEAD.
    write_lease("liv-nopid", -1, "a", with_pid=False)
    no_phantom = not watch.has_live_listener("liv-nopid")
    pruned_nopid = watch.gc_dead_leases("liv-nopid")
    record("0.5 missing-pid: no 'pid' -> DEAD via guard + gc'd (no immortal phantom)",
             no_phantom and pruned_nopid >= 1 and not watch.has_live_listener("liv-nopid"))
    record("0.5 guard: _proc_alive(0) and (-1) are False; a real pid is True",
             not watch._proc_alive(0) and not watch._proc_alive(-1) and watch._proc_alive(alive_pid))

    # DUPLICATE scope: two LIVE leases SAME scope -> flagged; DIFFERENT scopes -> not flagged.
    write_lease("liv-dup", alive_pid, "a")
    write_lease("liv-dup", alive_pid, "b")
    record("0.5 duplicate: two live listeners on the SAME scope -> flagged",
             watch.duplicate_listener_scopes("liv-dup") == ["*/*"])
    write_lease("liv-scoped", alive_pid, "inbox", conv="*", board="*")
    write_lease("liv-scoped", alive_pid, "perboard", conv="c1", board="b1")
    record("0.5 duplicate: inbox '*' vs per-board are DIFFERENT scopes -> NOT flagged",
             watch.duplicate_listener_scopes("liv-scoped") == [])

    # SESSION-NAME (0.6 ALFA): the binding is written from CLAUDE_CODE_SESSION_ID, atomically,
    # and resolved via boards_root()/.sessions/<sid> (same root as the hook -> cannot diverge).
    sessions = boards.boards_root() / ".sessions"
    _saved = os.environ.get("CLAUDE_CODE_SESSION_ID")
    os.environ["CLAUDE_CODE_SESSION_ID"] = "sid-test-123"
    watch._record_session_binding(boards.slug("worker-x"))
    bound = sessions / "sid-test-123"
    record("0.5 session-name: binding session->name written atomically",
             bound.is_file() and bound.read_text(encoding="utf-8").strip() == "worker-x")
    record("0.5 session-name: unknown sid -> no mapping (hook fails open)",
             not (sessions / "sid-absent").exists())
    # traversal guard: a sid with '/' or '..' must write NOTHING outside .sessions.
    os.environ["CLAUDE_CODE_SESSION_ID"] = "../escape"
    watch._record_session_binding(boards.slug("worker-x"))
    record("0.5 session-name: traversal sid rejected (nothing escapes .sessions)",
             not (boards.boards_root() / "escape").exists())
    if _saved is None:
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
    else:
        os.environ["CLAUDE_CODE_SESSION_ID"] = _saved


def check_req_tracking(boards, watchdog) -> None:
    """Point B: a REQ-ID minted at the source is tracked; the RESULT closes it. Pure read."""
    boards.join("v2", "req", "alfa")
    boards.say("v2", "req", "alfa", "REQUEST: REQ-alfa-001 write something in my domain")
    open_reqs = watchdog.open_requests(watchdog._all_messages())
    record("open REQ detected by ID", "REQ-alfa-001" in open_reqs)

    # a third party's mention does NOT close (only a RESULT closes)
    boards.say("v2", "req", "beta", "I saw REQ-alfa-001, waiting too")
    still = watchdog.open_requests(watchdog._all_messages())
    record("a third party's mention does not close the REQ", "REQ-alfa-001" in still)

    boards.say("v2", "req", "coordinator", "RESULT REQ-alfa-001: AUTHORIZED")
    after = watchdog.open_requests(watchdog._all_messages())
    record("the RESULT closes the REQ", "REQ-alfa-001" not in after)

    # batch case (real bug 2026-06-10): RESULT for one ID + mention of ANOTHER ID
    # on the 'still open' line must NOT close the second
    boards.say("v2", "req", "alfa", "REQUEST: REQ-alfa-002 commit, double signature")
    boards.say("v2", "req", "alfa", "REQUEST: REQ-alfa-003 in-domain write")
    boards.say("v2", "req", "coordinator",
               "BATCH.\nRESULT REQ-alfa-003: AUTHORIZED.\n"
               "STILL OPEN: REQ-alfa-002 (in signature package to the human).")
    final = watchdog.open_requests(watchdog._all_messages())
    record("batch: the RESULT closes only its own ID (line-level)",
             "REQ-alfa-003" not in final and "REQ-alfa-002" in final)

    # real case 2026-06-10: owner 'claude-dati' minting a short ID 'REQ-dati-NNN'
    boards.say("v2", "req", "claude-zeta", "REQUEST: REQ-zeta-001 commit my layer")
    with_prefix = watchdog.open_requests(watchdog._all_messages())
    record("short ID minted by a long name (claude-zeta -> REQ-zeta-NNN) open",
             "REQ-zeta-001" in with_prefix)


def check_protocol_isolation(boards) -> None:
    """Protocol-channels contract: bidirectional isolation by construction."""
    boards.board_dir("blindness", "run1__a").joinpath("_presence").mkdir(parents=True, exist_ok=True)

    boards.say("blindness", "run1__a", "control-room", "run SEED, channel A")
    boards.say("blindness", "run1__a", "analyst-1", "dossier analysis")
    write_ok = len(boards.list_messages("blindness", "run1__a")) == 2
    record("protocol identities write to blindness/*", write_ok)

    blocked_team = False
    try:
        boards.say("blindness", "run1__a", "alfa", "team intrusion")
    except PermissionError:
        blocked_team = True
    record("team member does NOT write to a protocol channel (leak in)", blocked_team)

    blocked_out = False
    try:
        boards.say("conv1", "board1", "analyst-1", "protocol escape")
    except PermissionError:
        blocked_out = True
    record("protocol identity does NOT write outside (leak out)", blocked_out)

    visible = boards.all_boards()
    with_protocol = boards.all_boards(include_protocollo=True)
    record("blindness/* excluded from cursors/inbox/watchdog",
             all(c != "blindness" for c, _ in visible)
             and any(c == "blindness" for c, _ in with_protocol))

    before = boards.inbox("alfa", update=False)
    record("an analyst's turn does not wake the team (clean inbox)",
             all(m.conv != "blindness" for m in before))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dialogue_selfcheck_") as tmp:
        os.environ["DIALOGUE_BOARDS_ROOT"] = os.path.join(tmp, "boards")
        os.environ["DIALOGUE_TEAM_ROOT"] = os.path.join(tmp, "team")

        # import AFTER the env override (boards_root/team_root read the env at runtime,
        # but the explicit order makes the isolation evident)
        from . import boards, identity, watch, guardian as watchdog

        print(f"Sandbox: {tmp}\n")
        check_storage(boards)
        check_watch_event_driven(boards, watch)
        check_race_pre_observer(boards, watch)
        check_identity(identity)
        check_inbox(boards)
        print("\n--- protocol v2 (2026-06-10 roundtable) ---")
        check_gap_recovery_cursor(boards, watch)
        check_to_guaranteed(boards, watch)
        check_concurrent_onboards(identity)
        check_req_tracking(boards, watchdog)
        check_lease_multi_listen(boards, watch, watchdog)
        check_liveness_and_alfa(boards, watch)
        if boards.PROTOCOL_CONVS:
            check_protocol_isolation(boards)
        else:
            record("protocol-channel isolation (SKIP: no channel configured)",
                     True, "feature present but unused by default")

    failed = [e for e in RESULTS if not e[1]]
    print(f"\n=== RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} ok ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
