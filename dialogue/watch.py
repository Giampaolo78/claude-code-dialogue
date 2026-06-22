"""
watch.py - event-driven listening (watchdog / FSEvents on macOS).

Replaces board.sh polling: `listen` blocks until a new message file appears
(or the timeout expires), waking on the filesystem event.
`stream` recursively watches ALL boards (dashboard for the human).

Robustness note: between the initial snapshot and the observer start a message
may already have arrived; after the start we re-check the list before going to
wait (no message lost, no race).
"""

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import boards


class _NewMessageHandler(FileSystemEventHandler):
    """Fires an Event on the first new message file in the watched directory."""

    def __init__(self, wake: threading.Event):
        self._wake = wake

    def _maybe_fire(self, path_str: str) -> None:
        if boards.is_message_file(Path(path_str)):
            self._wake.set()

    def on_created(self, event):
        if not event.is_directory:
            self._maybe_fire(event.src_path)

    def on_moved(self, event):
        # the atomic write (tmp + os.replace) generates a moved event
        if not event.is_directory:
            self._maybe_fire(event.dest_path)


def _lease_path(name: str):
    """
    PER-PROCESS lease: <name>.<pid>.json. A name can have N parallel listens
    (different boards): each process deposits and removes ONLY its own lease.
    Fixes the systematic false-DEAF (2026-06-10): with one file per name, the first
    listen to exit erased the listening-proof of another still-active one.
    """
    import os as _os
    import uuid as _uuid
    d = boards.boards_root() / ".leases"
    d.mkdir(parents=True, exist_ok=True)
    # pid + unique token: covers both separate processes and parallel listens
    # in the same process (threads) — each listen instance has its OWN lease
    return d / f"{boards.slug(name)}.{_os.getpid()}.{_uuid.uuid4().hex[:8]}.json"


# ---------------------------------------------------------------------------
# DLG-001 part-2: per-name single-committer via a commit-gate on "newest-live-lease"
# (no lock, no kill). The live agent is the latest re-arm -> it commits;
# older orphans yield. Scope: only the cursor path (wait_inbox/dlg inbox).
# ---------------------------------------------------------------------------

def _proc_alive(pid) -> bool:
    import os as _os
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    if pid <= 0:
        # os.kill semantics for pid<=0 are SPECIAL (0 = caller's process group, -1 = all the user's
        # processes, <-1 = a process group) -> all return success but NONE means "this listener is
        # alive". A real listener pid is always > 0. A malformed lease (missing 'pid' -> -1) must read
        # DEAD so it gets gc'd and never shows as a phantom 'LISTENING (pid -1)'. (anticorpo worker2)
        return False
    try:
        _os.kill(pid, 0)
        return True
    except OSError:
        return False


def _lease_uuid(path) -> str:
    # <name>.<pid>.<uuid>.json -> <uuid>
    parts = path.name.split(".")
    return parts[-2] if len(parts) >= 4 else ""


def _iter_leases(name_s: str):
    """(path, pid, armed_at, uuid) for each lease of the name. Robust to malformed files."""
    import json as _json
    d = boards.boards_root() / ".leases"
    out = []
    if not d.is_dir():
        return out
    for p in list(d.glob(f"{name_s}.*.json")):
        try:
            meta = _json.loads(p.read_text(encoding="utf-8"))
            pid = int(meta.get("pid", -1))
            armed = float(meta.get("armed_at", 0.0))
        except (OSError, ValueError, TypeError, _json.JSONDecodeError):
            continue
        out.append((p, pid, armed, _lease_uuid(p)))
    return out


def gc_dead_leases(name_s: str) -> int:
    """Prunes the name's leases with a dead PID. Returns how many it pruned."""
    n = 0
    for p, pid, _armed, _uuid in _iter_leases(name_s):
        if not _proc_alive(pid):
            try:
                p.unlink(missing_ok=True)
                n += 1
            except OSError:
                pass
    return n


def _record_session_binding(name_s: str) -> None:
    """0.6 ALFA: bind THIS Claude session -> name, so the Stop-hook can resolve WHICH listener to
    check (a project can host several Claude instances). Source: CLAUDE_CODE_SESSION_ID. Atomic write
    (no torn read if the hook fires mid-write). If there's no session id, skip -> the hook finds no
    mapping and exits 0 (a non-dialogue Claude in the same project must never be blocked)."""
    import os as _os
    sid = _os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if not sid or "/" in sid or "\\" in sid or sid in (".", ".."):
        return
    d = boards.boards_root() / ".sessions"
    d.mkdir(parents=True, exist_ok=True)
    boards._atomic_write(d / sid, name_s)
    _gc_stale_sessions(d)


def _gc_stale_sessions(d, keep: int = 200) -> None:
    """Opportunistic cleanup of old session->name mappings: harmless when stale (has_live_listener
    stays authoritative via the lease), only clutter. Keeps the most-recent `keep`, drops the rest."""
    try:
        files = sorted([p for p in d.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for p in (files[:-keep] if len(files) > keep else []):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def arm_listener(name: str, timeout: float = 0.0) -> dict:
    """
    Prepares the cursor listen: GC of the name's dead leases, then deposits its OWN lease
    (with armed_at) and returns it. The lease lives for the WHOLE listen (release_listener
    removes it), so the end-of-listen commit-gate sees the competing leases.
    """
    import json as _json
    import os as _os
    import time as _time
    name_s = boards.slug(name)
    (boards.boards_root() / ".leases").mkdir(parents=True, exist_ok=True)
    gc_dead_leases(name_s)
    _record_session_binding(name_s)  # 0.6 ALFA: session->name for the Stop-hook
    armed_at = _time.time()
    path = _lease_path(name_s)
    boards._atomic_write(path, _json.dumps({
        "pid": _os.getpid(), "conv": "*", "board": "*",
        "armed_at": armed_at, "timeout": timeout, "expires_at": armed_at + timeout,
    }))
    return {"path": path, "armed_at": armed_at, "uuid": _lease_uuid(path), "name": name_s}


def release_listener(info: dict) -> None:
    try:
        info["path"].unlink(missing_ok=True)
    except (OSError, KeyError):
        pass


def is_current_committer(name: str, my_armed_at: float, my_uuid: str) -> bool:
    """
    Commit-gate: True if NO LIVE lease of the name is newer than mine (greater armed_at,
    or equal with a greater uuid as tie-break). So only the latest live re-arm commits;
    older orphans yield (their delivery becomes a harmless duplicate, does not advance the
    cursor). NO process is killed.
    """
    name_s = boards.slug(name)
    for _p, pid, armed, uuid in _iter_leases(name_s):
        if uuid == my_uuid:
            continue
        if not _proc_alive(pid):
            continue
        if (armed, uuid) > (my_armed_at, my_uuid):
            return False
    return True


def live_listener_pids(name: str) -> list:
    """PIDs of the name's currently-live listeners. The lease pid IS os.getpid() of the listener
    process (NOT the zsh wrapper) -> the single source of truth for liveness (cf. 0.1 / pid-identity).
    Order is glob order (not armed-time); callers that need one pid take [0].
    NB: inherits _proc_alive's PID-reuse blindness (a reused dead pid reads alive) -> PLAN sec.8, non-blocking."""
    name_s = boards.slug(name)
    return [pid for _p, pid, _a, _u in _iter_leases(name_s) if _proc_alive(pid)]


def has_live_listener(name: str) -> bool:
    """Is there a live listener (live lease) for the name? Used by `dlg inbox` (single-committer)
    and `dlg status` (liveness column). Derived from live_listener_pids -> single liveness source."""
    return bool(live_listener_pids(name))


def duplicate_listener_scopes(name: str) -> list:
    """Scopes (conv/board) on which the name has MORE THAN ONE live listener. Harmless by design
    (the is_current_committer commit-gate keeps the cursor correct -> only the newest commits), so
    `dlg status` SURFACES it as info, it does NOT kill (cf. 0.2 / D2). Scope-aware: the global
    `--name` inbox listen (conv/board '*'/'*') and a per-board `--per` listen are DIFFERENT scopes
    and legitimately coexist -> not flagged."""
    import json as _json
    name_s = boards.slug(name)
    d = boards.boards_root() / ".leases"
    counts = {}
    if d.is_dir():
        for p in list(d.glob(f"{name_s}.*.json")):
            try:
                meta = _json.loads(p.read_text(encoding="utf-8"))
                if not _proc_alive(int(meta.get("pid", -1))):
                    continue
                scope = (meta.get("conv", "*"), meta.get("board", "*"))
            except (OSError, ValueError, TypeError, _json.JSONDecodeError):
                continue
            counts[scope] = counts.get(scope, 0) + 1
    return [f"{c}/{b}" for (c, b), n in counts.items() if n > 1]


# Paths currently watched by an Observer in THIS process (see wait_new_messages).
_watched_paths: set = set()
_watched_lock = threading.Lock()


def wait_new_messages(conv: str, board: str, timeout: float = 600.0,
                      per: str = None, name: str = None) -> list[boards.Message]:
    """
    Blocks until new messages arrive on the board (or timeout).
    Returns the messages new since the moment of the call ([] on timeout).

    per: if given, wakes ONLY for messages relevant to that name
    (dest == name or broadcast 'all'); messages addressed to others do not
    interrupt the wait (avoids empty wake-ups that cost a turn).

    name: identity of the listener. Deposits a LEASE file (pid, board,
    expiry) while listening is active: it's the measurable proof that the member
    is not deaf (defensive countermeasure — the watchdog detects members without
    a lease and raises the alarm to the human). If absent, use `per`.
    """
    bd = boards.board_dir(conv, board)
    if not bd.is_dir():
        raise FileNotFoundError(f"Board does not exist: {bd}")

    import json as _json
    import os as _os
    import time as _time
    identity = name or per
    lease = _lease_path(identity) if identity else None
    if lease:
        boards._atomic_write(lease, _json.dumps({
            "pid": _os.getpid(), "conv": boards.slug(conv), "board": boards.slug(board),
            "armed_at": _time.time(), "timeout": timeout,
            "expires_at": _time.time() + timeout,
        }))

    def relevant(paths: list) -> list[boards.Message]:
        msgs = [boards.parse_message(p) for p in sorted(paths)]
        if per:
            name = boards.slug(per)
            msgs = [m for m in msgs if m.dest in ("all", name) and m.author != name]
        return msgs

    deadline = time.monotonic() + timeout
    before = set(boards.list_messages(conv, board))
    wake = threading.Event()
    path_key = str(bd)
    # Avoid double-scheduling the SAME path on two Observers in ONE process: macOS
    # FSEvents raises 'already scheduled' (harmless, but prints an ugly traceback). A
    # second concurrent listen on the same path falls back to polling. Production never
    # hits this (one listen = one process); it surfaces only in same-process tests.
    with _watched_lock:
        own_observer = path_key not in _watched_paths
        if own_observer:
            _watched_paths.add(path_key)
    observer = None
    if own_observer:
        try:
            observer = Observer()
            observer.schedule(_NewMessageHandler(wake), path_key, recursive=False)
            observer.start()
        except Exception:                      # observer setup failed -> fall back to polling, no leak
            if observer is not None:
                try:
                    observer.stop()
                except Exception:
                    pass
            observer = None
            with _watched_lock:
                _watched_paths.discard(path_key)
            own_observer = False
    try:
        while True:
            # race-check: did something arrive between snapshot and wait?
            arrived = set(boards.list_messages(conv, board)) - before
            good = relevant(arrived)
            if good:
                return good
            before |= arrived  # filtered out: must not wake again
            wake.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return []
            # a listen WITHOUT its own observer (path already watched in-process) must
            # re-check by polling, so cap its wait; an event-driven listen waits fully.
            wake.wait(timeout=remaining if own_observer else min(remaining, 1.0))
    finally:
        if observer is not None:
            observer.stop()
            observer.join()
            with _watched_lock:
                _watched_paths.discard(path_key)
        if lease:
            try:
                lease.unlink(missing_ok=True)
            except OSError:
                pass


class _RelevantHandler(FileSystemEventHandler):
    """Wakes when a message relevant to `name` arrives (dest to them or broadcast)."""

    def __init__(self, wake: threading.Event, name: str):
        self._wake = wake
        self._name = name

    def _maybe_fire(self, path_str: str) -> None:
        path = Path(path_str)
        if not boards.is_message_file(path) or path.parent.name.startswith(("_", ".")):
            return
        try:
            msg = boards.parse_message(path)
        except (OSError, ValueError):
            return
        if msg.author != self._name and msg.dest in ("all", self._name):
            self._wake.set()

    def on_created(self, event):
        if not event.is_directory:
            self._maybe_fire(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._maybe_fire(event.dest_path)


def wait_inbox(name: str, timeout: float = 600.0,
               commit: bool = True,
               manage_lease: bool = True,
               cursor: str = "read") -> tuple[list[boards.Message], int]:
    """
    Point E of protocol v2 (single cursor): delivers ALL unread IMMEDIATELY
    from the inbox's durable cursor (all boards, --to included: point F) and
    exits; if there's nothing, waits for the first relevant message and delivers it.
    A message dropped in a re-arm gap is thus recovered at the moment of the
    next re-arm: a silent stall is impossible by construction.
    Deposits the lease for the whole wait.

    Returns (new, max_seen). DLG-001:
    - commit=True (default): advances the cursor internally (IN-PROCESS callers, e.g. selfcheck).
    - commit=False: does NOT commit; the caller (cmd_listen) commits AFTER writing+flushing
      the output -> a kill/crash between delivery and flush re-delivers (duplicate), does not lose.
    """
    name_s = boards.slug(name)
    root = boards.boards_root()
    root.mkdir(parents=True, exist_ok=True)

    import json as _json
    import os as _os
    import time as _time
    # DLG-001 part-2: with manage_lease=False the lease is managed by the caller (cmd_listen,
    # via arm_listener/release_listener) to also cover the commit. IN-PROCESS callers
    # (default True) deposit their own lease here as before.
    lease = None
    if manage_lease:
        lease = _lease_path(name_s)
        boards._atomic_write(lease, _json.dumps({
            "pid": _os.getpid(), "conv": "*", "board": "*",
            "armed_at": _time.time(), "timeout": timeout,
            "expires_at": _time.time() + timeout,
        }))

    wake = threading.Event()
    observer = Observer()
    observer.schedule(_RelevantHandler(wake, name_s), str(root), recursive=True)
    observer.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            new_msgs, max_seen = boards.peek(name_s, cursor=cursor)
            if new_msgs:
                if commit:
                    boards.commit(name_s, max_seen, cursor=cursor)
                return new_msgs, max_seen
            wake.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if commit:
                    boards.commit(name_s, max_seen, cursor=cursor)
                return [], max_seen
            wake.wait(timeout=remaining)
    finally:
        observer.stop()
        observer.join()
        if lease is not None:
            try:
                lease.unlink(missing_ok=True)
            except OSError:
                pass


class _StreamHandler(FileSystemEventHandler):
    """Forwards every new message file (on any board) to a callback."""

    def __init__(self, on_message: Callable[[boards.Message], None]):
        self._on_message = on_message
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def _maybe_emit(self, path_str: str) -> None:
        path = Path(path_str)
        if not boards.is_message_file(path):
            return
        if path.parent.name.startswith(("_", ".")):
            return
        with self._lock:
            if path_str in self._seen:
                return
            self._seen.add(path_str)
        try:
            self._on_message(boards.parse_message(path))
        except (OSError, ValueError):
            pass  # file gone or malformed: must not kill the dashboard

    def on_created(self, event):
        if not event.is_directory:
            self._maybe_emit(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._maybe_emit(event.dest_path)


def stream_all(on_message: Callable[[boards.Message], None],
               stop_event: Optional[threading.Event] = None) -> None:
    """
    Recursively watches the boards root and calls on_message for every
    new message. Blocks until stop_event is set (or forever).
    """
    root = boards.boards_root()
    root.mkdir(parents=True, exist_ok=True)

    observer = Observer()
    observer.schedule(_StreamHandler(on_message), str(root), recursive=True)
    observer.start()
    try:
        if stop_event is None:
            stop_event = threading.Event()
        while not stop_event.is_set():
            stop_event.wait(timeout=1.0)
    finally:
        observer.stop()
        observer.join()
