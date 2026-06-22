"""
boards.py - board storage.

Philosophy inherited from board.sh (battle-tested): ONE file per message, a sortable
and unique name (microsecond timestamp + pid), no lock, no write race. The write is
atomic (tmp + os.replace) so watchers never read partial messages.

On-disk structure:
    dialogue/boards/<conv>/_topic.md
    dialogue/boards/<conv>/<board>/<micros>_<pid>__<author>.md
    dialogue/boards/<conv>/<board>/_presence/<author>
    dialogue/boards/.checkpoints/<member>.json     (inbox state, not a message)
"""

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
# Code root on which the watchdog resolves the owners' domain directories
# (backend/, frontend/, ...). Defaults two levels above this file; override with
# DIALOGUE_PROJECT_ROOT to point it at the actual project root.
PROJECT_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# Protocol channels: a generic mechanism for isolated side-channels (a turn does not
# wake the team; the watchdog cannot write to them: leak impossible by construction).
# Off by default -> empty sets = feature disabled. To re-enable, populate with the
# dedicated convs/identities (and restore the isolation check).
PROTOCOL_CONVS: set[str] = set()
PROTOCOL_IDENTITIES: set[str] = set()


def boards_root() -> Path:
    """Boards root. Override with DIALOGUE_BOARDS_ROOT (used by the self-check)."""
    env = os.environ.get("DIALOGUE_BOARDS_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent / "boards"


def project_root() -> Path:
    """Code root for resolving domain dirs. Override with DIALOGUE_PROJECT_ROOT."""
    env = os.environ.get("DIALOGUE_PROJECT_ROOT")
    return Path(env) if env else PROJECT_ROOT_DEFAULT


HEADER_RE = re.compile(r"^### (?P<autore>\S+) -> (?P<dest>\S+)\s+·\s+(?P<ts>.+)$")


def slug(text: str) -> str:
    """Normalize: lowercase, only [a-z0-9_-], no duplicates."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    return s


def now_human() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def micros() -> int:
    return time.time_ns() // 1000


@dataclass
class Message:
    """A board message, with the metadata extracted from the file."""
    conv: str
    board: str
    path: Path
    micros: int
    author: str
    dest: str
    text: str  # full file content

    @property
    def eot(self) -> bool:
        return "-- out (EOT)" in self.text


def conv_dir(conv: str) -> Path:
    return boards_root() / slug(conv)


def board_dir(conv: str, board: str) -> Path:
    return conv_dir(conv) / slug(board)


def is_message_file(path: Path) -> bool:
    name = path.name
    return name.endswith(".md") and not name.startswith((".", "_"))


def list_messages(conv: str, board: str) -> list[Path]:
    """Message files in chronological order (the filename sorts them)."""
    bd = board_dir(conv, board)
    if not bd.is_dir():
        return []
    return sorted(p for p in bd.iterdir() if p.is_file() and is_message_file(p))


def parse_message(path: Path) -> Message:
    """Extracts metadata from the filename and the header. Robust to anomalous files."""
    text = path.read_text(encoding="utf-8")
    name_match = re.match(r"^(\d+)_\d+__(.+)\.md$", path.name)
    ts_us = int(name_match.group(1)) if name_match else 0
    author_from_name = name_match.group(2) if name_match else "unknown"

    author, dest = author_from_name, "all"
    first_line = text.split("\n", 1)[0]
    header = HEADER_RE.match(first_line)
    if header:
        author = header.group("autore")
        dest = header.group("dest")

    return Message(
        conv=path.parent.parent.name,
        board=path.parent.name,
        path=path,
        micros=ts_us,
        author=author,
        dest=dest,
        text=text,
    )


def _atomic_write(target: Path, content: str) -> None:
    tmp = target.parent / f".tmp_{os.getpid()}_{micros()}"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def set_topic(conv: str, text: str) -> bool:
    """Sets the topic. Atomic: first wins. Returns False if already present."""
    cd = conv_dir(conv)
    cd.mkdir(parents=True, exist_ok=True)
    tf = cd / "_topic.md"
    try:
        with open(tf, "x", encoding="utf-8") as f:
            f.write(f"TOPIC: {text}\n\n(set {now_human()})\n")
        return True
    except FileExistsError:
        return False


def get_topic(conv: str) -> Optional[str]:
    tf = conv_dir(conv) / "_topic.md"
    return tf.read_text(encoding="utf-8") if tf.is_file() else None


def join(conv: str, board: str, name: str) -> dict:
    """Join a board: registers presence, returns state (topic, present, messages)."""
    name = slug(name)
    bd = board_dir(conv, board)
    presence = bd / "_presence"
    presence.mkdir(parents=True, exist_ok=True)
    already_present = (presence / name).exists()
    (presence / name).touch()
    return {
        "name": name,
        "already_present": already_present,
        "topic": get_topic(conv),
        "present": present_members(conv, board),
        "messages": list_messages(conv, board),
    }


def present_members(conv: str, board: str) -> list[str]:
    presence = board_dir(conv, board) / "_presence"
    if not presence.is_dir():
        return []
    return sorted(p.name for p in presence.iterdir() if p.is_file())


def say(conv: str, board: str, name: str, text: str,
        dest: str = "all", eot: bool = False) -> Path:
    """Writes a message (closes with 'over', or EOT). Returns the file path."""
    name = slug(name)
    dest = slug(dest) if dest != "all" else "all"
    conv_slug = slug(conv)
    # bidirectional isolation of the protocol channels (by construction)
    if conv_slug in PROTOCOL_CONVS and name not in PROTOCOL_IDENTITIES:
        raise PermissionError(
            f"'{name}' is not a protocol identity: cannot write to {conv_slug}/*"
        )
    if name in PROTOCOL_IDENTITIES and conv_slug not in PROTOCOL_CONVS:
        raise PermissionError(
            f"'{name}' is a protocol identity: writes ONLY to channels {PROTOCOL_CONVS}"
        )
    bd = board_dir(conv, board)
    if not bd.is_dir():
        raise FileNotFoundError(
            f"Board does not exist: {bd}. Run join first."
        )
    presence = bd / "_presence"
    presence.mkdir(exist_ok=True)
    (presence / name).touch()

    footer = f"-- out (EOT) {name}" if eot else f"-- over {name}"
    content = (
        f"### {name} -> {dest}  ·  {now_human()}\n"
        f"{text}\n\n"
        f"{footer}\n"
    )
    target = bd / f"{micros()}_{os.getpid()}__{name}.md"
    _atomic_write(target, content)

    if eot:
        (presence / name).unlink(missing_ok=True)
    return target


def read_board(conv: str, board: str) -> list[Message]:
    """Full transcript, in order."""
    return [parse_message(p) for p in list_messages(conv, board)]


def all_boards(include_protocollo: bool = False) -> list[tuple[str, str]]:
    """
    All existing (conv, board) pairs. Protocol channels are EXCLUDED by default:
    the team's cursors/inbox/watchdog never see them (protocol-channels contract).
    include_protocollo=True only for human observability.
    """
    root = boards_root()
    out = []
    if not root.is_dir():
        return out
    for cd in sorted(root.iterdir()):
        if not cd.is_dir() or cd.name.startswith("."):
            continue
        if cd.name in PROTOCOL_CONVS and not include_protocollo:
            continue
        for bd in sorted(cd.iterdir()):
            if bd.is_dir() and not bd.name.startswith(("_", ".")):
                out.append((cd.name, bd.name))
    return out


def archive_board(conv: str, board: str) -> Path:
    """
    Board lifecycle: archive a FINISHED board. Moves boards/<conv>/<board> to
    boards/<conv>/_archive/<board>/ -- EXCLUDED from the active views (all_boards skips '_' dirs)
    -- and marks the archival instant for retention. REVERSIBLE (it's a move).
    """
    import shutil
    board_s = slug(board)
    src = conv_dir(conv) / board_s
    if not src.is_dir():
        raise FileNotFoundError(f"Board does not exist: {src}")
    arch = conv_dir(conv) / "_archive"
    arch.mkdir(parents=True, exist_ok=True)
    dst = arch / board_s
    if dst.exists():                      # already archived with the same name -> suffix it
        dst = arch / f"{board_s}__{micros()}"
    shutil.move(str(src), str(dst))
    (dst / "_archived_at").write_text(str(time.time()), encoding="utf-8")
    return dst


def gc_archive(retention_days: float = 7.0) -> list[str]:
    """
    Board lifecycle: PERMANENTLY deletes boards archived more than retention_days ago.
    Operates ONLY on boards/<conv>/_archive/ (NEVER on the live ones). Returns the purged paths.
    """
    import shutil
    root = boards_root()
    purged: list[str] = []
    if not root.is_dir():
        return purged
    now = time.time()
    cutoff = retention_days * 86400.0
    for cd in root.iterdir():
        arch = cd / "_archive"
        if not arch.is_dir():
            continue
        for bd in arch.iterdir():
            if not bd.is_dir():
                continue
            marker = bd / "_archived_at"
            try:
                archived_at = (float(marker.read_text(encoding="utf-8"))
                               if marker.is_file() else bd.stat().st_mtime)
            except (OSError, ValueError):
                archived_at = bd.stat().st_mtime
            if now - archived_at > cutoff:
                try:
                    shutil.rmtree(bd)
                    purged.append(f"{cd.name}/_archive/{bd.name}")
                except OSError:
                    pass
    return purged


def _recap_lock(cdir: Path, wait_s: float = 5.0, stale_s: float = 30.0) -> Optional[Path]:
    """Mutex via ATOMIC mkdir (with stale-steal against deadlock from a dead holder).
    Returns the Path of the acquired lock, or None if it can't within wait_s."""
    lock = cdir / ".recap_lock"
    deadline = time.time() + wait_s
    while True:
        try:
            lock.mkdir()
            return lock
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_s:
                    lock.rmdir()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                return None
            time.sleep(0.05)


def recap_open(conv: str, ttl_s: float = 900.0) -> tuple:
    """
    Team standup. Returns (alignment_board, created: bool). ATOMIC race-safe CREATE-OR-JOIN:
    all workers of the same round CONVERGE on ONE board. A `.recap_current` pointer
    (board + expiry_us) protected by an mkdir mutex: within the TTL you JOIN; once expired,
    a new round opens. created=True ONLY for whoever creates the round.
    """
    cdir = conv_dir(conv)
    cdir.mkdir(parents=True, exist_ok=True)
    ptr = cdir / ".recap_current"
    lock = _recap_lock(cdir)
    try:
        cur = None
        if ptr.is_file():
            try:
                name, exp = ptr.read_text(encoding="utf-8").split()
                cur = (name, int(exp))
            except (OSError, ValueError):
                cur = None
        if cur and cur[1] > micros():
            return cur[0], False
        board = f"allineamento_{micros()}"
        (cdir / board).mkdir(parents=True, exist_ok=True)
        _atomic_write(ptr, f"{board} {micros() + int(ttl_s * 1_000_000)}")
        return board, True
    finally:
        if lock is not None:
            try:
                lock.rmdir()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Inbox / checkpoint (autonomous-owner pattern)
# ---------------------------------------------------------------------------

def _checkpoint_path(name: str) -> Path:
    cp_dir = boards_root() / ".checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    return cp_dir / f"{slug(name)}.json"


def _load_cursors(name: str) -> tuple[int, int]:
    """
    Loads (delivered_us, read_us) from the checkpoint. Backward-compat: the old single
    cursor `last_seen_us` counts as BOTH (so existing checkpoints don't break).
    """
    cp = _checkpoint_path(slug(name))
    if not cp.is_file():
        return 0, 0
    try:
        d = json.loads(cp.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0, 0
    legacy = d.get("last_seen_us", 0)
    return d.get("delivered_us", legacy), d.get("read_us", legacy)


def peek(name: str, cursor: str = "read") -> tuple[list[Message], int]:
    """
    Returns (new, max_seen) WITHOUT advancing any cursor. DLG two-cursor:
    - cursor="read" (default, INBOX path): new = not yet marked read (--done)
      -> the inbox re-shows ALL unread until you --done (the NET, no miss even if you
      look at the inbox instead of the listen output).
    - cursor="delivered" (LISTEN path): new = not yet delivered by the listen
      -> a re-arm does NOT re-deliver the same ones (no busy-loop), compatible with ARM-FIRST.
    max_seen = highest micros seen across all boards (the value to advance the cursor to).
    """
    name = slug(name)
    delivered, read = _load_cursors(name)
    base = delivered if cursor == "delivered" else read

    new_msgs: list[Message] = []
    max_seen = base
    for conv, board in all_boards():
        for path in list_messages(conv, board):
            msg = parse_message(path)
            max_seen = max(max_seen, msg.micros)
            if msg.micros <= base:
                continue
            if msg.author == name:
                continue
            if msg.dest not in ("all", name):
                continue
            new_msgs.append(msg)

    new_msgs.sort(key=lambda m: m.micros)
    return new_msgs, max_seen


def commit(name: str, max_seen: int, cursor: str = "read") -> None:
    """
    Advances a member's cursor to max_seen (forward-only, idempotent). Two-cursor:
    - cursor="delivered": advances ONLY `delivered_us` (the listen delivered, not read).
    - cursor="read" (default): advances `read_us` (--done) AND `delivered_us` (read => delivered).
    """
    name = slug(name)
    delivered, read = _load_cursors(name)
    if cursor == "delivered":
        delivered = max(delivered, max_seen)
    else:
        read = max(read, max_seen)
        delivered = max(delivered, max_seen)
    _atomic_write(_checkpoint_path(name),
                  json.dumps({"delivered_us": delivered, "read_us": read}))


def inbox(name: str, update: bool = True) -> list[Message]:
    """
    UNREAD messages for a member (the `read` cursor), across ALL boards. Includes the
    broadcasts (dest=all) and those addressed to them; excludes their own. update=True: marks
    them read (advances read+delivered) -- for IN-PROCESS callers. The CLI default is peek
    (non-destructive) + --done.
    """
    new_msgs, max_seen = peek(name, cursor="read")
    if update:
        commit(name, max_seen, cursor="read")
    return new_msgs
