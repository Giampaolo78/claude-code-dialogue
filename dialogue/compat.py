"""
compat.py - cross-platform shims so the dialogue engine runs on Windows too.

The engine was written Unix-first. Three primitives are Unix-only:
  - fcntl.flock          registry lock (identity.py)
  - os.kill(pid, 0)      liveness check (watch.py, guardian.py) -- on Windows
                         os.kill TERMINATES for sig 0, so it must NEVER be used
                         to "check if alive": it would kill the probed process.
  - os.kill(pid, SIG)    graceful stop of listener/watchdog (cli.py, guardian.py)

This module isolates them. The UNIX path is byte-for-byte the previous behaviour
(zero regression on Mac/Linux); only Windows gets new code.

Windows process introspection uses `psutil` (declared as a win32-only dependency);
the file lock uses stdlib `msvcrt`.
"""
import os
import sys

IS_WINDOWS = sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# Exclusive file lock  (was: fcntl.flock(fh, LOCK_EX) / LOCK_UN)
# ---------------------------------------------------------------------------
if IS_WINDOWS:
    import msvcrt
    import time as _time

    def lock_exclusive(fh):
        """Blocking exclusive lock on an open file handle (locks 1 byte at 0).
        msvcrt.LK_LOCK gives up after ~10s with OSError; we retry so the lock BLOCKS
        like fcntl.flock (the registry RMW it guards is brief -> contention is rare).
        (behavior-match noted by worker2: flock blocks forever, raw LK_LOCK would raise)."""
        fh.seek(0)
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                _time.sleep(0.1)

    def unlock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def lock_exclusive(fh):
        fcntl.flock(fh, fcntl.LOCK_EX)

    def unlock(fh):
        fcntl.flock(fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Liveness check  (was: os.kill(pid, 0) -> raises OSError if dead)
# CRITICAL: on Windows os.kill(pid, 0) calls TerminateProcess -> it would KILL
# the very process being probed. Never use os.kill for liveness here.
# ---------------------------------------------------------------------------
def pid_alive(pid) -> bool:
    """True iff `pid` is a live process. pid<=0 -> False (POSIX gives 0/-1 special
    process-group semantics that would false-positive; we never want them)."""
    if pid is None or pid <= 0:
        return False
    if IS_WINDOWS:
        import psutil
        return psutil.pid_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours


# ---------------------------------------------------------------------------
# Stop a process  (was: os.kill(pid, SIG))
# Unix: send `unix_sig`. Windows: hard terminate (no SIGINT/SIGTERM to a pid).
# USED ONLY BY guardian.stop (the WATCHDOG): stop() drops the watchdog lease
# DIRECTLY, so a hard kill that skips the target's `finally` leaves no zombie.
# The LISTENER stop does NOT use this -> it uses a cooperative SENTINEL
# (watch.request_stop + wait_inbox): for the listener a hard kill would skip the
# `finally` that releases its lease, and the gc-belt races too early (gc runs
# before the kill completes) -> lease-zombie. (anticorpo worker2)
# ---------------------------------------------------------------------------
def stop_pid(pid, unix_sig) -> bool:
    """Stop process `pid` -- WATCHDOG only (the listener uses a cooperative sentinel).
    On Unix sends `unix_sig` (SIGTERM); on Windows hard-terminates. Returns True if the
    stop was issued (False if pid is gone/invalid)."""
    if pid is None or pid <= 0:
        return False
    if IS_WINDOWS:
        import psutil
        try:
            psutil.Process(pid).terminate()
            return True
        except psutil.NoSuchProcess:
            return False
    os.kill(pid, unix_sig)
    return True
