#!/usr/bin/env python3
"""Exclusive-GPU-work interlock, operator CLI (see ops/PRODUCTION-CONTRACT.md).

    python scripts/gpu_lock.py status                       # who holds it, stale or not; exit 0 free / 1 held
    python scripts/gpu_lock.py run --purpose "bakeoff" -- scripts/bakeoff-session.sh
    python scripts/gpu_lock.py clear [--force]              # remove a stale lock; --force also a live one

Takes GPU_LOCK_PATH from .env (default /etc/ai-server/bakeoff.lock, the WP-H convention).
Nothing here signals or kills a process: `clear` only removes the file, and refuses a live
holder without --force.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import load_config  # noqa: E402
from aiserver import gpulock  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--path", help="lock file (default: GPU_LOCK_PATH from .env)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("run")
    r.add_argument("--purpose", required=True)
    r.add_argument("argv", nargs=argparse.REMAINDER, help="command to run while holding the lock (after --)")
    c = sub.add_parser("clear")
    c.add_argument("--force", action="store_true", help="remove even if the holder looks live (still kills nothing)")
    args = ap.parse_args(argv)
    path = gpulock.resolve_path(args.path, load_config())

    if args.cmd == "status":
        record = gpulock.read_record(path)
        if record is None and not path.exists():
            print(f"free: {path}")
            return 0
        stale, reason = gpulock.staleness(record)
        print(f"held: {path}")
        if record:
            print(f"  owner={record.owner} pid={record.pid} host={record.host} since={record.started}")
            print(f"  purpose={record.purpose}\n  cleanup={record.expected_cleanup}")
        print(f"  stale={'yes' if stale else 'no'} ({reason})")
        return 1

    if args.cmd == "run":
        cmd = [a for a in args.argv if a != "--"]
        if not cmd:
            print("[FAIL] run: no command given after --", file=sys.stderr)
            return 2
        try:
            return gpulock.run_under_lock(path, cmd, purpose=args.purpose)
        except gpulock.LockError as e:
            print(f"[FAIL] {e}", file=sys.stderr)
            return 3

    try:
        record = gpulock.clear(path, stale_only=not args.force)
    except gpulock.LockHeldError as e:
        print(f"[FAIL] refusing to clear a live lock: {e} (use --force only if you are sure)", file=sys.stderr)
        return 3
    print("nothing to clear" if record is None and not path.exists() else f"cleared {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
