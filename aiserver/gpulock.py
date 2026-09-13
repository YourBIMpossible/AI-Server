"""Exclusive-GPU-work interlock.

One file, one holder. Taken by work that must own the whole card -- runner swaps, full
bakeoffs, GPU-monopolising eval runs, long-context stress probes -- and by nothing else.
Ordinary inference and read-only analysis never touch it (see ops/PRODUCTION-CONTRACT.md).

The file is the WP-H convention: ``/etc/ai-server/bakeoff.lock`` (Personal-OCR reads the same
path through ``WP_H_BAKEOFF_LOCK`` and drops to CPU while it exists). ``GPU_LOCK_PATH`` in
``.env`` overrides the location.

Semantics:

* acquire = atomic ``O_CREAT|O_EXCL`` create of the file holding a JSON record (schema below).
  Contention raises ``LockHeldError`` carrying the other holder's record and a staleness verdict.
* release = remove the file, but only if the record still names *this* acquisition (owner
  token + pid); a foreign record is never removed.
* stale = holder pid not alive on this host, or the record older than ``max_age_s``. Staleness
  is **reported, never acted on**: nothing here kills a process or deletes a foreign lock by
  itself. ``clear()`` is the operator's explicit recovery and refuses a live holder unless forced.
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import uuid

SCHEMA = "aiserver.gpulock/1"
DEFAULT_PATH = "/etc/ai-server/bakeoff.lock"
DEFAULT_MAX_AGE_S = 6 * 3600  # a bakeoff session is ~2h; anything past this is suspect


class LockError(RuntimeError):
    pass


class LockHeldError(LockError):
    def __init__(self, path: Path, record: "LockRecord | None", stale: bool, reason: str):
        self.path, self.record, self.stale, self.reason = path, record, stale, reason
        who = f"{record.owner} pid {record.pid} on {record.host} since {record.started}" if record else "unreadable record"
        hint = " (looks stale: %s -- `scripts/gpu_lock.py clear` after checking)" % reason if stale else ""
        super().__init__(f"GPU lock {path} held by {who}{hint}")


@dataclass(frozen=True)
class LockRecord:
    schema: str
    owner: str        # human-readable command / purpose owner
    command: str      # argv that took the lock
    pid: int
    host: str
    started: str      # ISO-8601 UTC
    purpose: str
    expected_cleanup: str  # what the operator should see when the holder is done
    token: str        # per-acquisition random id; release checks it

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "LockRecord":
        obj = json.loads(text)
        if obj.get("schema") != SCHEMA:
            raise LockError(f"unknown lock schema {obj.get('schema')!r}")
        return cls(**{k: obj[k] for k in cls.__dataclass_fields__})


def resolve_path(explicit: str | os.PathLike | None = None, cfg=None) -> Path:
    """explicit arg > Config.gpu_lock_path > GPU_LOCK_PATH env > WP-H default."""
    if explicit:
        return Path(explicit)
    if cfg is not None and getattr(cfg, "gpu_lock_path", ""):
        return Path(cfg.gpu_lock_path)
    return Path(os.environ.get("GPU_LOCK_PATH") or DEFAULT_PATH)


def pid_alive(pid: int) -> bool | None:
    """True/False for this host; None when it cannot be determined."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        SYNCHRONIZE, STILL_ACTIVE = 0x00100000, 259
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k32.OpenProcess(SYNCHRONIZE | 0x0400, False, pid)  # + PROCESS_QUERY_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return None
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_record(path: Path) -> LockRecord | None:
    try:
        return LockRecord.from_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, LockError, TypeError):
        return None


def staleness(record: LockRecord | None, *, max_age_s: float = DEFAULT_MAX_AGE_S, now: float | None = None) -> tuple[bool, str]:
    """(stale?, reason). Unreadable records are stale; foreign-host records are judged by age only."""
    if record is None:
        return True, "record unreadable"
    now = time.time() if now is None else now
    try:
        started = datetime.fromisoformat(record.started).timestamp()
    except ValueError:
        return True, "unparseable start time"
    age = now - started
    if age > max_age_s:
        return True, f"age {age / 3600:.1f}h exceeds {max_age_s / 3600:.1f}h"
    if record.host == socket.gethostname():
        alive = pid_alive(record.pid)
        if alive is False:
            return True, f"pid {record.pid} not running"
    return False, "holder appears live" if record.host == socket.gethostname() else "held from another host; liveness unknown"


def acquire(path: Path, *, purpose: str, owner: str | None = None, expected_cleanup: str = "lock file removed by holder") -> LockRecord:
    path = Path(path)
    if not purpose.strip():
        raise LockError("purpose is required")
    record = LockRecord(
        schema=SCHEMA,
        owner=owner or os.path.basename(sys.argv[0] or "python"),
        command=" ".join(sys.argv),
        pid=os.getpid(),
        host=socket.gethostname(),
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        purpose=purpose,
        expected_cleanup=expected_cleanup,
        token=uuid.uuid4().hex,
    )
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        other = read_record(path)
        stale, reason = staleness(other)
        raise LockHeldError(path, other, stale, reason) from None
    except FileNotFoundError:
        raise LockError(f"lock directory {path.parent} does not exist -- see ops/PRODUCTION-CONTRACT.md") from None
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(record.to_json())
    return record


def release(path: Path, record: LockRecord) -> bool:
    """Remove the lock only if it is still ours. Returns False if it was not (nothing removed)."""
    current = read_record(Path(path))
    if current is None or current.token != record.token or current.pid != record.pid:
        return False
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    return True


def clear(path: Path, *, stale_only: bool = True, max_age_s: float = DEFAULT_MAX_AGE_S) -> LockRecord | None:
    """Operator recovery. Removes the file; with stale_only (default) refuses a live holder.
    Never signals or kills the holder."""
    path = Path(path)
    record = read_record(path)
    if record is None and not path.exists():
        return None
    stale, reason = staleness(record, max_age_s=max_age_s)
    if stale_only and not stale:
        raise LockHeldError(path, record, False, reason)
    os.remove(path)
    return record


@contextmanager
def held(path: Path, *, purpose: str, owner: str | None = None, expected_cleanup: str = "lock file removed by holder") -> Iterator[LockRecord]:
    """acquire(); yield; release() -- release runs on success, exception and KeyboardInterrupt."""
    record = acquire(path, purpose=purpose, owner=owner, expected_cleanup=expected_cleanup)
    try:
        yield record
    finally:
        release(path, record)


def run_under_lock(path: Path, argv: list[str], *, purpose: str, owner: str | None = None) -> int:
    """Hold the lock for the lifetime of a child process; return its exit status.
    A Ctrl-C reaches the child too (same process group); we wait for it, then release."""
    with held(path, purpose=purpose, owner=owner or argv[0], expected_cleanup=f"{argv[0]} exits"):
        proc = subprocess.Popen(argv)
        try:
            return proc.wait()
        except KeyboardInterrupt:
            proc.wait()
            return 130
