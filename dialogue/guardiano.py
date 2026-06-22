"""
watchdog.py - anti-freeze guardian of the dialogue system (v2, table protocol
2026-06-10). Run by the COORDINATOR.

Declared technical limit: NO process can inject a turn into a deaf Claude
session. The watchdog does not wake: it DETECTS and ALERTS whoever can act — the
coordinator (a reminder on the board) and the human (a macOS notification with the exact point).

Detectors (v2 — voted at the table, points B/H/I of the package):
  1. OPEN REQUESTS by REQ-ID: a request is open if a message from its OWNER
     contains an ID minted at the source (REQ-<owner>-<nnn>) and no later message
     contains the same ID together with 'RESULT'. Reminders ONLY to the debtor
     (the coordinator), at increasing intervals (1x threshold, 3x threshold), then
     escalation to the human (macOS) once only. NEVER string-match on free text:
     the tracking is a pure read of the IDs.
  2. DEAF via lease: a member with no active listen (lease), no filesystem
     activity, past the grace period -> DIRECT notification to the human.
     Applies ALSO to the coordinator (criterion: no lease + no messages).
  3. GLOBAL FREEZE: open requests + prolonged total silence -> critical.

Usage (by the coordinator, in background):
    .venv/bin/python -m dialogue watchdog [--interval 60] [--threshold 600]
"""

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from . import boards

AUTHOR_WATCHDOG = "watchdog"
# Board dedicated to the watchdog's system alerts (DEAF/reminder/escalation/
# freeze). The coordinator listens to it (via the global cursor), NOT the owners: keeping
# the alerts out of the coordination board avoids the all-in-one dumpster and, with
# dest=coordinatore, doesn't wake the owners. (protocol fix 2026-06-13)
SYSTEM_BOARD = "sistema"
REQ_RE = re.compile(r"\bREQ-([a-z0-9_]+)-(\d+)\b")
RESULT_MARKER = "RESULT"
FREEZE_THRESHOLD_S = 1200.0
GRACE_DEAF_S = 180.0

PING_TEXT = ("PING: what's your status? Answer briefly. If you are STUCK waiting for "
              "authorization, re-state the REQUEST with its REQ-ID in COMPLETE, "
              "self-contained form. If you are working, just say on what.")


# ---------------------------------------------------------------------------
# persistent state
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    return boards.boards_root() / ".watchdog_state.json"


def _load_state() -> dict:
    p = _state_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict) -> None:
    boards._atomic_write(_state_path(), json.dumps(state, indent=2))


def _notify_macos(text: str) -> bool:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{text}" with title "dialogue watchdog"'],
            capture_output=True, timeout=5,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _all_messages() -> list[boards.Message]:
    out = []
    for conv, board in boards.all_boards():
        out.extend(boards.read_board(conv, board))
    out.sort(key=lambda m: m.micros)
    return out


def _eta_s(msg: boards.Message, now_us: int) -> float:
    return (now_us - msg.micros) / 1_000_000


def _mtime_recent(dirs: list[str]) -> float:
    import os
    newest = 0.0
    for d in dirs:
        base = boards.project_root() / d
        if not base.is_dir():
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                try:
                    newest = max(newest, (Path(root) / f).stat().st_mtime)
                except OSError:
                    continue
    return newest


def _lease_valid(slug: str) -> bool:
    """
    Valid if THERE EXISTS AT LEAST ONE live lease for the name (per-process lease:
    a name can have N parallel listens). Dead leases (pid down or expired) are
    pruned here, opportunistically.
    """
    import os
    d = boards.boards_root() / ".leases"
    if not d.is_dir():
        return False
    alive = False
    for p in list(d.glob(f"{slug}.*.json")) + [d / f"{slug}.json"]:  # + legacy
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            expired = time.time() > data.get("expires_at", 0)
            os.kill(int(data.get("pid", -1)), 0)
            pid_alive = True
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            expired, pid_alive = True, False
        if pid_alive and not expired:
            alive = True
        else:
            try:
                p.unlink(missing_ok=True)  # prune dead lease
            except OSError:
                pass
    return alive


# ---------------------------------------------------------------------------
# detectors
# ---------------------------------------------------------------------------

def open_requests(msgs: list[boards.Message]) -> dict:
    """
    Open REQ-IDs: {rid: {owner, opened_us, conv, board}}. An ID is OPEN if it
    appears in a message from its owner (ID prefix == author) and NO later message
    cites it together with 'RESULT'. Pure read: the minting is at the source.
    """
    def is_own(owner_part: str, author_slug: str) -> bool:
        # 'REQ-dati-001' minted by 'claude-dati': the ID's owner-part matches if
        # it is the whole name or one of its components (separators - and _)
        return owner_part == author_slug or owner_part in re.split(r"[-_]+", author_slug)

    open_reqs: dict = {}
    closed_reqs: set = set()
    for m in msgs:
        if m.author == AUTHOR_WATCHDOG:
            continue
        author_slug = boards.slug(m.author)
        # LINE-level closing: 'RESULT' and the ID must be on the same line
        # (a batch mentioning an ID on a 'still open' line does NOT close it)
        for line in m.text.split("\n"):
            if RESULT_MARKER not in line:
                continue
            for match in REQ_RE.finditer(line):
                if not is_own(match.group(1), author_slug):
                    closed_reqs.add(match.group(0))
        for match in REQ_RE.finditer(m.text):
            rid = match.group(0)
            owner = match.group(1)
            if is_own(owner, author_slug) and rid not in open_reqs:
                open_reqs[rid] = {"owner": owner, "opened_us": m.micros,
                               "conv": m.conv, "board": m.board}
    return {rid: info for rid, info in open_reqs.items() if rid not in closed_reqs}


def detect_reminders(msgs: list[boards.Message], state: dict, threshold_s: float) -> list[dict]:
    """Reminders for open REQs: ONLY to the coordinator (debtor), increasing intervals."""
    now_us = boards.micros()
    levels = state.setdefault("req_level", {})
    out = []
    for rid, info in open_requests(msgs).items():
        eta = (now_us - info["opened_us"]) / 1_000_000
        level = levels.get(rid, 0)
        if level == 0 and eta > threshold_s:
            out.append({"type": "reminder", "key": rid, "level": 1,
                        "debtor": "coordinatore",
                        "detail": f"{rid} from {info['owner']} without RESULT for {int(eta/60)}min"})
        elif level == 1 and eta > 3 * threshold_s:
            out.append({"type": "escalation", "key": rid, "level": 2,
                        "debtor": "umano",
                        "detail": (f"{rid} from {info['owner']} without RESULT for {int(eta/60)}min "
                                      f"despite reminder: the coordinator is not responding")})
    return out


def detect_deaf(msgs: list[boards.Message], members: list[dict], state: dict,
                 threshold_s: float) -> list[dict]:
    """
    DEAF = no valid lease + no activity (fs for the owners, messages for the
    coordinator) + past grace. DIRECT notification to the human: the deaf one does
    not read the board by definition.
    """
    now_ts = time.time()
    now_us = boards.micros()
    missing = state.setdefault("deaf_missing_since", {})
    out = []
    for m in members:
        if m.get("status") != "active":
            continue
        name = m["slug"]
        if _lease_valid(name):
            missing.pop(name, None)
            continue
        # Liveness for ALL members: a recent post on the board PROVES the member
        # is alive. (false-DEAF fix 2026-06-13: a heads-down/read-only owner doesn't
        # write domain files but is active; their board post proves it.
        # Before, the credit was only the coordinator's -> owners who were reasoning
        # got marked DEAF despite having just spoken.)
        own = [x for x in msgs if x.author == name]
        recent_post = bool(own) and _eta_s(own[-1], now_us) < threshold_s
        if name == "coordinatore":
            active_recently = recent_post
        else:
            mt = _mtime_recent(m.get("dirs") or [])
            active_recently = recent_post or (bool(mt) and (now_ts - mt) < threshold_s)
        if active_recently:
            missing.pop(name, None)
            continue
        since = missing.setdefault(name, now_ts)
        if now_ts - since < GRACE_DEAF_S:
            continue
        out.append({"type": "deaf", "key": f"deaf:{name}", "debtor": name,
                    "detail": (f"{name} DEAF: no active listen, no activity — "
                                  f"needs a human nudge in its terminal")})
    return out


def detect_freeze(msgs: list[boards.Message]) -> list[dict]:
    relevant = [m for m in msgs if m.author != AUTHOR_WATCHDOG]
    if not relevant or not open_requests(msgs):
        return []
    silence = _eta_s(relevant[-1], boards.micros())
    if silence <= FREEZE_THRESHOLD_S:
        return []
    return [{"type": "global_freeze", "key": f"freeze:{relevant[-1].path.name}",
             "debtor": "umano",
             "detail": (f"FREEZE: open requests and no message for "
                           f"{int(silence/60)}min — needs nudges in the terminals")}]


# ---------------------------------------------------------------------------
# loop
# ---------------------------------------------------------------------------

def _emit(wake: dict, conv: str, _board: str, state: dict) -> None:
    kind = wake["type"]
    text = f"[{kind.upper()}] {wake['detail']}"
    # All alerts go to the SISTEMA board, addressed to the COORDINATOR.
    # Why dest=coordinatore and not dest=all: the owners' listen is a global
    # cursor (wait_inbox) that wakes on every message with dest in {all, their_name};
    # a dest=all woke them all on every DEAF (self-amplifying churn). Addressing
    # only the coordinator leaves them in peace; the human is still reached by the
    # macOS notification. (protocol fix 2026-06-13)
    boards.board_dir(conv, SYSTEM_BOARD).mkdir(parents=True, exist_ok=True)
    if kind == "reminder":
        boards.say(conv, SYSTEM_BOARD, AUTHOR_WATCHDOG, text, dest="coordinatore")
        state["req_level"][wake["key"]] = 1
    elif kind == "escalation":
        boards.say(conv, SYSTEM_BOARD, AUTHOR_WATCHDOG, text, dest="coordinatore")
        _notify_macos(wake["detail"])
        state["req_level"][wake["key"]] = 2
    elif kind == "deaf":
        boards.say(conv, SYSTEM_BOARD, AUTHOR_WATCHDOG, text, dest="coordinatore")
        _notify_macos(wake["detail"])
        state["deaf_missing_since"].pop(wake["debtor"], None)  # re-alarm after new grace
    elif kind == "global_freeze":
        boards.say(conv, SYSTEM_BOARD, AUTHOR_WATCHDOG, text, dest="coordinatore")
        _notify_macos(wake["detail"])


def run(interval_s: float = 60.0, threshold_s: float = 600.0,
           one_pass: bool = False) -> None:
    state = _load_state()
    state.setdefault("req_level", {})
    state.setdefault("deaf_missing_since", {})
    print(f"[WATCHDOG v2] active: scan {interval_s:.0f}s, threshold {threshold_s:.0f}s, "
          f"REQ-ID tracking, deaf-detection via lease (coordinator included)", flush=True)

    while True:
        msgs = _all_messages()
        if msgs:
            conv, board = msgs[-1].conv, msgs[-1].board
            try:
                from . import identity
                members = identity.load_registry().get("members", [])
            except (OSError, ValueError):
                members = []
            event_list = (detect_reminders(msgs, state, threshold_s)
                      + detect_deaf(msgs, members, state, threshold_s)
                      + detect_freeze(msgs))
            for ev in event_list:
                _emit(ev, conv, board, state)
                print(f"[WATCHDOG v2] {ev['type']}: {ev['detail']}", flush=True)
            _save_state(state)
        # lifecycle board: periodic purge of expired archived boards (7-day retention)
        try:
            purged = boards.gc_archive()
            if purged:
                print(f"[WATCHDOG v2] archive-gc: purged {len(purged)} boards archived >7d",
                      flush=True)
        except OSError:
            pass
        if one_pass:
            return
        time.sleep(interval_s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="watchdog v2 (coordinator)")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--threshold", type=float, default=600.0)
    ap.add_argument("--one-pass", dest="one_pass", action="store_true")
    args = ap.parse_args(argv)
    try:
        run(args.interval, args.threshold, args.one_pass)
    except KeyboardInterrupt:
        print("\n[WATCHDOG v2] stopped.", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())