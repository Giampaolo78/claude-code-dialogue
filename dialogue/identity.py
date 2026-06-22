"""
identity.py - registration and team registry.

Registration ties a NAME to a MANDATE (domain), not to a process: a session that
resumes the role inherits name, mandate and board history. The registry
(team/registry.json) is the source of truth for identities and prevents
collisions by design.
"""

import fcntl
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from .boards import REPO_ROOT, slug, _atomic_write

MODEL_DEFAULT = "claude-fable-5"


@contextmanager
def _registry_lock():
    """
    Exclusive lock on registry writes (point G of protocol v2).
    Fixes the read-modify-write race that on 2026-06-10 silently erased
    claude-dati's registration (two concurrent registrations, lost update).
    """
    team_root().mkdir(parents=True, exist_ok=True)
    lockfile = team_root() / ".registry.lock"
    fh = open(lockfile, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _journal(wake: dict) -> None:
    """Append-only registry journal: no identity write without a trace."""
    wake = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **wake}
    with open(team_root() / "registry_journal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(wake, ensure_ascii=False) + "\n")


def team_root() -> Path:
    """Team root. Override with DIALOGUE_TEAM_ROOT (used by the self-check)."""
    env = os.environ.get("DIALOGUE_TEAM_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent / "team"


def registry_path() -> Path:
    return team_root() / "registry.json"


def load_registry() -> dict:
    rp = registry_path()
    if not rp.is_file():
        return {"project": "default", "members": []}
    try:
        reg = json.loads(rp.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        # Do NOT return a default here: the write path (onboard) would save over the
        # corrupt file, losing the roster. Better a clear error -> file left intact.
        raise ValueError(f"registry unreadable/corrupt: {rp} ({e}). "
                         f"Not touching it to avoid data loss: check it by hand.")
    if not isinstance(reg, dict):
        raise ValueError(f"invalid registry (not a JSON object): {rp}")
    reg.setdefault("members", [])   # tolerate a file without 'members' (empty roster)
    # backward-compat: registries written before the English key rename used IT keys.
    # Map them to the new names on read, so old registries keep working transparently.
    _legacy_keys = {"dominio": "domain", "mandato": "mandate", "modello": "model",
                    "nato_il": "joined_at", "stato": "status"}
    for _m in reg["members"]:
        for _old, _new in _legacy_keys.items():
            if _old in _m and _new not in _m:
                _m[_new] = _m.pop(_old)
        if _m.get("status") == "attivo":
            _m["status"] = "active"
    return reg


def save_registry(reg: dict) -> None:
    team_root().mkdir(parents=True, exist_ok=True)
    _atomic_write(registry_path(), json.dumps(reg, indent=2, ensure_ascii=False) + "\n")


def find_member(reg: dict, name: str) -> Optional[dict]:
    # '-' and '_' are equivalent in the comparison: confusable names = same identity
    s = slug(name).replace("-", "_")
    for m in reg["members"]:
        if m["slug"].replace("-", "_") == s:
            return m
    return None


def onboard(name: str, domain: str, mandate: Optional[str] = None,
              model: str = MODEL_DEFAULT, dirs: Optional[list] = None) -> dict:
    """
    Register a new identity. Raises ValueError if the name already exists
    (collisions are prevented here, not handled later).
    """
    from .boards import PROTOCOL_IDENTITIES
    if slug(name) in (PROTOCOL_IDENTITIES | {"watchdog"}):
        raise ValueError(
            f"Name '{name}' reserved for the protocol/system: cannot be registered."
        )
    with _registry_lock():
        reg = load_registry()
        if find_member(reg, name):
            raise ValueError(
                f"Name '{name}' already registered. Registration is unique: "
                f"to resume the role you don't need to re-register."
            )
        member = {
            "name": name,
            "slug": slug(name),
            "domain": domain,
            "mandate": mandate,
            "model": model,
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "active",
            "dirs": dirs or [],  # domain directories (watchdog)
        }
        reg["members"].append(member)
        save_registry(reg)
        _journal({"event": "registration", "member": member})
    return member


def set_terminal_title(title: str) -> bool:
    """
    Best-effort: writes the title escape directly to the tty.
    Inside a Claude Code Bash tool stdout is captured, so we try /dev/tty;
    if it's absent (sandbox/headless) we fail silently.
    """
    seq = f"\033]0;{title}\007"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(seq)
            tty.flush()
        return True
    except OSError:
        try:
            sys.stdout.write(seq)
            sys.stdout.flush()
            return False
        except OSError:
            return False
