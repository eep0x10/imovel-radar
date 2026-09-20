import json

import pytest

from app import search_jobs, services, storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("IMOVEL_DB_PATH", str(tmp_path / "jobs.sqlite3"))
    storage.initialize()
    with storage.transaction() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", (uid, f"user{uid}@example.test", "Teste", "unused", "{}", storage.now_iso()))
        for sid, uid, enabled in ((1, 1, 1), (2, 1, 1), (3, 2, 1), (4, 1, 0)):
            conn.execute("INSERT INTO sources(id,user_id,name,kind,enabled,authorized,created_at) VALUES(?,?,?,'portal',?,1,?)", (sid, uid, f"Fonte {sid}", enabled, storage.now_iso()))


def test_frozen_profile_active_reuse_and_account_isolation(db, monkeypatch):
    requested = {**storage.DEFAULT_PROFILE, "area_min": 70, "area_max": 100}
    initial = search_jobs.enqueue(1, requested)
    repeated = search_jobs.enqueue(1, requested)
    assert repeated["id"] == initial["id"] and repeated["reused"]
    calls = []
    monkeypatch.setattr(services, "refresh_source", lambda uid, sid, *, search_profile: calls.append((uid, sid, search_profile["area_min"])) or {"inserted": 1})
    assert search_jobs.process(1)["state"] == "complete"
    assert calls == [(1, 1, 70), (1, 2, 70)]
    assert search_jobs.status(2) is None
    requested["area_min"] = 90
    assert search_jobs.enqueue(1, requested)["id"] != initial["id"]


def test_partial_errors_redacted_and_progress(db, monkeypatch):
    search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    def refresh(uid, sid, *, search_profile):
        if sid == 2:
            raise ValueError("secret-key=https://private.example/token")
        return {"inserted": 2, "coverage": {"complete": False, "pages": 2, "url": "secret"}, "warnings": ["secret"]}
    monkeypatch.setattr(services, "refresh_source", refresh)
    job = search_jobs.process(1)
    assert job["state"] == "partial" and job["completed"] == 2
    assert job["sources"][0]["warnings_count"] == 1
    assert "secret" not in json.dumps(job)
    assert job["sources"][1]["state"] == "error"


def test_no_sources_and_all_failed(db, monkeypatch):
    with storage.transaction() as conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE user_id=2")
    empty = search_jobs.enqueue(2, storage.DEFAULT_PROFILE)
    assert empty["state"] == "error" and empty["total"] == 0
    search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    def fail(*args, **kwargs):
        raise RuntimeError("private")
    monkeypatch.setattr(services, "refresh_source", fail)
    assert search_jobs.process(1)["state"] == "error"


def test_lease_excludes_duplicate_and_recovery_resumes_only_remaining(db, monkeypatch):
    search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    owner = services.acquire_lock("search-job:1")
    calls = []
    monkeypatch.setattr(services, "refresh_source", lambda uid, sid, **kwargs: calls.append(sid) or {})
    assert search_jobs.process(1)["state"] == "pending"
    assert calls == []
    services.release_lock("search-job:1", owner)
    with storage.transaction() as conn:
        job = search_jobs._read(conn, 1)
        job["state"] = "running"
        job["sources"][0]["state"] = "complete"
        job["sources"][1]["state"] = "running"
        search_jobs._write(conn, 1, job)
    assert search_jobs.process_pending()[0]["state"] == "complete"
    assert calls == [2]
    assert search_jobs.process_pending() == []


def test_invalid_profile_never_creates_job(db):
    with pytest.raises(ValueError):
        search_jobs.enqueue(1, {"area_min": 90, "area_max": 70})
    assert search_jobs.status(1) is None


def test_pending_changed_request_replaced_before_worker_claim(db, monkeypatch):
    initial = search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    latest = search_jobs.enqueue(1, {**storage.DEFAULT_PROFILE, "area_min": 65})
    assert initial["id"] != latest["id"] and not latest["reused"]
    calls = []
    monkeypatch.setattr(services, "refresh_source", lambda uid, sid, *, search_profile: calls.append(search_profile["area_min"]) or {})
    search_jobs.process(1)
    assert calls == [65, 65]


def test_running_changed_requests_durable_latest_wins(db, monkeypatch):
    initial = search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    calls = []
    def refresh(uid, sid, *, search_profile):
        calls.append(search_profile["area_min"])
        if len(calls) == 1:
            queued = search_jobs.enqueue(1, {**storage.DEFAULT_PROFILE, "area_min": 60})
            assert queued["queued"] and queued["next_profile"]["area_min"] == 60
        elif len(calls) == 2:
            assert search_jobs.status(1)["next_profile"]["area_min"] == 60
            search_jobs.enqueue(1, {**storage.DEFAULT_PROFILE, "area_min": 70})
        return {}
    monkeypatch.setattr(services, "refresh_source", refresh)
    completed = search_jobs.process(1)
    assert completed["id"] == initial["id"] and completed["state"] == "complete"
    replacement = search_jobs.status(1)
    assert replacement["id"] != initial["id"] and replacement["state"] == "pending"
    assert replacement["profile"]["area_min"] == 70
    search_jobs.process_pending()
    assert calls == [35, 35, 70, 70]


def test_latest_running_snapshot_cancels_older_queue(db, monkeypatch):
    search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    def refresh(uid, sid, *, search_profile):
        search_jobs.enqueue(1, {**storage.DEFAULT_PROFILE, "area_min": 70})
        same = search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
        assert same["reused"] and not same["queued"]
        return {}
    monkeypatch.setattr(services, "refresh_source", refresh)
    search_jobs.process(1)
    assert search_jobs.status(1)["state"] == "complete"
    assert search_jobs.status(1)["next_profile"] is None
