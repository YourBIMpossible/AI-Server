"""aiserver/gpulock.py: acquire/release, contention, stale detection, non-destructive recovery."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from aiserver import gpulock
from aiserver.gpulock import LockHeldError, LockError, LockRecord, acquire, clear, held, release, staleness


def test_acquire_writes_schema_record_and_release_removes(tmp_path):
    path = tmp_path / "bakeoff.lock"
    rec = acquire(path, purpose="unit test")
    data = json.loads(path.read_text())
    assert data["schema"] == gpulock.SCHEMA
    assert data["pid"] == os.getpid() and data["purpose"] == "unit test"
    for key in ("owner", "command", "host", "started", "expected_cleanup"):
        assert data[key]
    assert release(path, rec) is True
    assert not path.exists()


def test_contention_reports_live_holder_and_leaves_file(tmp_path):
    path = tmp_path / "bakeoff.lock"
    rec = acquire(path, purpose="first")
    with pytest.raises(LockHeldError) as ei:
        acquire(path, purpose="second")
    assert ei.value.stale is False and ei.value.record.purpose == "first"
    assert path.exists()
    release(path, rec)


def test_release_refuses_foreign_record(tmp_path):
    path = tmp_path / "bakeoff.lock"
    mine = acquire(path, purpose="mine")
    foreign = LockRecord(**{**mine.__dict__, "token": "other", "pid": 999999})
    assert release(path, foreign) is False
    assert path.exists()
    assert release(path, mine) is True


def test_stale_by_dead_pid_and_by_age():
    now = datetime.now(timezone.utc)
    base = dict(schema=gpulock.SCHEMA, owner="x", command="x", host=gpulock.socket.gethostname(),
                purpose="p", expected_cleanup="c", token="t")
    dead = LockRecord(pid=2**22 + 12345, started=now.isoformat(timespec="seconds"), **base)
    stale, reason = staleness(dead)
    assert stale and "not running" in reason
    old = LockRecord(pid=os.getpid(), started=(now - timedelta(hours=7)).isoformat(timespec="seconds"), **base)
    stale, reason = staleness(old)
    assert stale and "age" in reason
    live = LockRecord(pid=os.getpid(), started=now.isoformat(timespec="seconds"), **base)
    assert staleness(live) == (False, "holder appears live")
    other_host = LockRecord(pid=1, started=now.isoformat(timespec="seconds"), **{**base, "host": "elsewhere"})
    assert staleness(other_host)[0] is False  # liveness unknown -> not declared stale by pid
    assert staleness(None)[0] is True


def test_clear_refuses_live_holder_and_never_signals(tmp_path, monkeypatch):
    path = tmp_path / "bakeoff.lock"
    rec = acquire(path, purpose="live")
    killed = []
    monkeypatch.setattr(os, "kill", lambda *a: killed.append(a) if a[1] != 0 else None)
    with pytest.raises(LockHeldError):
        clear(path)
    assert path.exists() and not killed
    assert clear(path, stale_only=False).token == rec.token  # forced: file removed, nothing signalled
    assert not path.exists() and not killed


def test_clear_removes_stale_lock(tmp_path):
    path = tmp_path / "bakeoff.lock"
    path.write_text("not json")
    assert clear(path) is None
    assert not path.exists()
    assert clear(path) is None  # idempotent on a free lock


def test_held_releases_on_exception_and_interrupt(tmp_path):
    path = tmp_path / "bakeoff.lock"
    with pytest.raises(RuntimeError):
        with held(path, purpose="boom"):
            assert path.exists()
            raise RuntimeError("boom")
    assert not path.exists()
    with pytest.raises(KeyboardInterrupt):
        with held(path, purpose="ctrl-c"):
            raise KeyboardInterrupt
    assert not path.exists()


def test_missing_directory_is_a_clear_error(tmp_path):
    with pytest.raises(LockError, match="does not exist"):
        acquire(tmp_path / "nope" / "bakeoff.lock", purpose="x")


def test_run_under_lock_holds_for_child_lifetime(tmp_path):
    path = tmp_path / "bakeoff.lock"
    probe = f"import os,sys; sys.exit(0 if os.path.exists({str(path)!r}) else 7)"
    rc = gpulock.run_under_lock(path, [sys.executable, "-c", probe], purpose="child")
    assert rc == 0 and not path.exists()


def test_resolve_path_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv("GPU_LOCK_PATH", raising=False)
    assert str(gpulock.resolve_path()) == str(gpulock.Path(gpulock.DEFAULT_PATH))
    monkeypatch.setenv("GPU_LOCK_PATH", "/x/env.lock")
    assert gpulock.resolve_path().as_posix().endswith("env.lock")

    class Cfg:
        gpu_lock_path = "/y/cfg.lock"

    assert gpulock.resolve_path(None, Cfg()).as_posix().endswith("cfg.lock")
    assert gpulock.resolve_path(tmp_path / "e.lock", Cfg()) == tmp_path / "e.lock"


def test_cli_status_run_clear(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(gpulock.Path(__file__).resolve().parent.parent / "scripts"))
    import gpu_lock as cli
    path = tmp_path / "bakeoff.lock"
    assert cli.main(["--path", str(path), "status"]) == 0
    assert "free" in capsys.readouterr().out
    rc = cli.main(["--path", str(path), "run", "--purpose", "t", "--", sys.executable, "-c", "print('in')"])
    assert rc == 0 and not path.exists()
    path.write_text("garbage")
    assert cli.main(["--path", str(path), "status"]) == 1
    assert "stale=yes" in capsys.readouterr().out
    assert cli.main(["--path", str(path), "clear"]) == 0 and not path.exists()
    assert cli.main(["--path", str(path), "run", "--purpose", "t"]) == 2
