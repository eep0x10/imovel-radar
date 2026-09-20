"""Scheduler and recovery invariants; no network and no persistent user database."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app import backup, storage, worker
from app.services import acquire_lock, ingest, release_lock


NOW = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("IMOVEL_DB_PATH", str(tmp_path / "active.sqlite3"))
    monkeypatch.setenv("IMOVEL_TIMEZONE", "America/Sao_Paulo")
    monkeypatch.setenv("IMOVEL_REFRESH_HOUR", "7")
    monkeypatch.setattr(storage, "now_iso", lambda: NOW.isoformat())
    storage.initialize()
    with storage.transaction() as conn:
        uid = conn.execute("INSERT INTO users(email,name,password_hash,profile,created_at) VALUES(?,?,?,?,?)", ("test@example.com", "Test", "unused-fixture", storage.dumps(storage.DEFAULT_PROFILE), NOW.isoformat())).lastrowid
        sid = conn.execute("INSERT INTO sources(user_id,name,kind,url,enabled,authorized,status,created_at) VALUES(?,?,'feed',?,1,1,'pending',?)", (uid, "Feed", "https://example.com/feed.json", NOW.isoformat())).lastrowid
        ingest(conn, uid, [{"source": "Feed", "external_id": "apt1", "price": 300000, "area": 50, "city": "São Paulo", "neighborhood": "Mooca", "property_type": "apartment", "bedrooms": 2, "status": "active", "observed_at": NOW.isoformat()}], "feed", sid)
        pid = conn.execute("SELECT id FROM properties").fetchone()[0]
        conn.execute("INSERT INTO tracking(user_id,property_id,saved,notes,updated_at) VALUES(?,?,1,?,?)", (uid, pid, "Keep this note", NOW.isoformat()))
    return {"uid": uid, "sid": sid, "pid": pid, "path": storage.db_path()}


def rows(sql, params=()):
    with closing(storage.connect()) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def test_worker_timezone_schedule_daily_idempotency_and_next_day(database, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "refresh_source", lambda uid, sid: calls.append((uid, sid)) or {"updated": 0})
    # 09:59 UTC is 06:59 São Paulo; the configured daily time is 07:00.
    assert worker.cycle(NOW.replace(hour=9, minute=59))["status"] == "waiting"
    assert not calls
    first = worker.cycle(NOW.replace(hour=10))
    assert first["results"][0]["status"] == "success"
    assert calls == [(database["uid"], database["sid"])]
    assert worker.cycle(NOW)["results"] == []
    assert worker.cycle(NOW, force=True)["results"] == []
    assert len(calls) == 1
    assert worker.cycle(NOW + timedelta(days=1))["results"][0]["status"] == "success"
    assert len(calls) == 2
    assert len(rows("SELECT * FROM daily_runs")) == 2
    assert not rows("SELECT * FROM locks")


def test_worker_local_day_and_unauthorized_disabled_sources(database, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "refresh_source", lambda uid, sid: calls.append(sid) or {})
    with storage.transaction() as conn:
        for name, enabled, authorized in (("Disabled", 0, 1), ("Unauthorized", 1, 0)):
            conn.execute("INSERT INTO sources(user_id,name,kind,url,enabled,authorized,created_at) VALUES(?,?,'feed',?,?,?,?)", (database["uid"], name, "https://example.com/feed", enabled, authorized, NOW.isoformat()))
    # 01:00 UTC on Sep 19 is still Sep 18 locally. Force bypasses hour only.
    worker.cycle(NOW.replace(hour=1), force=True)
    assert calls == [database["sid"]]
    assert rows("SELECT day FROM daily_runs")[0]["day"] == "2026-09-18"


def test_worker_failed_attempt_cooldown_retry_and_snapshot_preservation(database, monkeypatch):
    before = rows("SELECT * FROM properties")
    observations = rows("SELECT * FROM observations")
    calls = []
    def failure(uid, sid):
        calls.append(sid)
        with storage.transaction() as conn:
            conn.execute("UPDATE sources SET status='error',last_attempt=? WHERE id=?", (NOW.isoformat(), sid))
        raise ValueError("fixture unavailable")
    monkeypatch.setattr(worker, "refresh_source", failure)
    result = worker.cycle(NOW)
    assert result["results"] == [{"source_id": database["sid"], "status": "failed"}]
    assert worker.cycle(NOW + timedelta(minutes=59))["results"] == []
    assert len(calls) == 1
    assert worker.cycle(NOW + timedelta(hours=1))["results"][0]["status"] == "failed"
    assert len(calls) == 2
    monkeypatch.setattr(worker, "refresh_source", lambda uid, sid: {"unchanged": 1})
    assert worker.cycle(NOW, force=True)["results"][0]["status"] == "success"
    assert rows("SELECT * FROM properties") == before
    assert rows("SELECT * FROM observations") == observations
    assert not rows("SELECT * FROM locks")


def test_worker_lease_busy_expired_owner_and_exception_release(database, monkeypatch):
    owner = acquire_lock("daily-cycle", minutes=15)
    assert owner
    monkeypatch.setattr(worker, "refresh_source", lambda uid, sid: pytest.fail("busy cycle must not refresh"))
    assert worker.cycle(NOW)["status"] == "busy"
    release_lock("daily-cycle", "wrong-owner")
    assert rows("SELECT owner FROM locks")[0]["owner"] == owner
    with storage.transaction() as conn:
        conn.execute("UPDATE locks SET expires_at=? WHERE name='daily-cycle'", ((NOW - timedelta(days=1)).isoformat(),))
    replacement = acquire_lock("daily-cycle")
    assert replacement and replacement != owner
    release_lock("daily-cycle", owner)
    assert rows("SELECT owner FROM locks")[0]["owner"] == replacement
    release_lock("daily-cycle", replacement)
    def unexpected(uid, sid):
        raise RuntimeError("unexpected fixture error")
    monkeypatch.setattr(worker, "refresh_source", unexpected)
    with pytest.raises(RuntimeError, match="unexpected fixture"):
        worker.cycle(NOW)
    assert not rows("SELECT * FROM locks")


def test_worker_heartbeat_and_invalid_hour(database, monkeypatch):
    worker.heartbeat()
    assert rows("SELECT value FROM runtime WHERE key='worker_heartbeat'")[0]["value"] == NOW.isoformat()
    monkeypatch.setenv("IMOVEL_REFRESH_HOUR", "24")
    with pytest.raises(ValueError):
        worker.cycle(NOW)


def test_online_backup_manifest_restore_and_no_overwrite(database, tmp_path):
    destination = tmp_path / "backups" / "snapshot.sqlite3"
    # Keep a live connection open and commit a write in WAL before online backup.
    with closing(storage.connect()) as live:
        live.execute("UPDATE tracking SET notes='Latest committed WAL note'")
        live.commit()
        result = backup.snapshot(destination)
    assert result["integrity_check"] == "ok"
    assert result["counts"] == {"users": 1, "properties": 1, "observations": 1, "tracking": 1, "sources": 1}
    assert result["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert json.loads(destination.with_suffix(".manifest.json").read_text()) == result
    with closing(storage.connect()) as live:
        live.execute("UPDATE tracking SET notes='Changed after backup'")
        live.commit()
    restored = tmp_path / "restore" / "verified.sqlite3"
    assert backup.restore_copy(destination, restored) == {"integrity_check": "ok", "properties": 1}
    with closing(sqlite3.connect(restored)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT notes FROM tracking").fetchone()[0] == "Latest committed WAL note"
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert rows("SELECT notes FROM tracking")[0]["notes"] == "Changed after backup"
    original_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        backup.snapshot(destination)
    with pytest.raises(ValueError):
        backup.restore_copy(destination, restored)
    with pytest.raises(ValueError):
        backup.restore_copy(destination, database["path"])
    with pytest.raises(ValueError):
        backup.restore_copy(destination, destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == original_hash


def test_restore_missing_source_does_not_create_destination(database, tmp_path):
    target = tmp_path / "restore.sqlite3"
    with pytest.raises(ValueError, match="Snapshot não encontrado"):
        backup.restore_copy(tmp_path / "missing.sqlite3", target)
    assert not target.exists()
