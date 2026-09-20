from datetime import datetime, timedelta, timezone

from app import alert_collection, search_jobs, services, storage
from tests.test_search_jobs import db


START = datetime(2026, 9, 20, 8, tzinfo=timezone.utc)  # 05:00 Sao Paulo


def saved(sid=1, enabled=1, area=70):
    with storage.transaction() as conn:
        conn.execute("INSERT INTO saved_searches(id,user_id,name,profile,enabled,created_at,updated_at) VALUES(?,1,'Alerta',?,?,?,?)",
                     (sid, storage.dumps({**storage.DEFAULT_PROFILE, "area_min": area, "area_max": 120}), enabled, START.isoformat(), START.isoformat()))


def test_first_immediate_frozen_filters_daily_hour_and_idempotency(db, monkeypatch):
    saved()
    calls = []
    monkeypatch.setattr(services, "refresh_source", lambda uid, sid, *, search_profile: calls.append(search_profile["area_min"]) or {})
    monkeypatch.setenv("IMOVEL_REFRESH_HOUR", "7")
    assert alert_collection.cycle(START)["status"] == "complete"
    assert calls == [70, 70]
    assert alert_collection.cycle(START + timedelta(hours=4))["status"] == "waiting"
    assert alert_collection.cycle(START + timedelta(days=1))["status"] == "waiting"
    assert alert_collection.cycle(START + timedelta(days=1, hours=2))["status"] == "complete"
    assert calls == [70, 70, 70, 70]


def test_paused_and_active_account_are_skipped(db, monkeypatch):
    saved(enabled=0)
    assert alert_collection.cycle(START)["status"] == "waiting"
    with storage.transaction() as conn:
        conn.execute("UPDATE saved_searches SET enabled=1")
    queued = search_jobs.enqueue(1, storage.DEFAULT_PROFILE)
    assert alert_collection.cycle(START)["status"] == "waiting"
    assert search_jobs.status(1)["id"] == queued["id"]


def test_failure_cooldown_and_no_enabled_sources(db):
    saved()
    with storage.transaction() as conn:
        conn.execute("UPDATE sources SET enabled=0")
    assert alert_collection.cycle(START)["status"] == "error"
    assert alert_collection.cycle(START + timedelta(minutes=59))["status"] == "waiting"
    assert alert_collection.cycle(START + timedelta(hours=1))["status"] == "error"


def test_only_one_due_alert_and_partial_counts_as_daily_completion(db, monkeypatch):
    saved(1, area=70)
    saved(2, area=90)
    calls = []
    monkeypatch.setattr(services, "refresh_source", lambda uid, sid, *, search_profile: calls.append(search_profile["area_min"]) or {"coverage": {"complete": False}})
    assert alert_collection.cycle(START)["search_id"] == 1
    assert calls == [70, 70]
    assert alert_collection.cycle(START)["search_id"] == 2
    assert calls == [70, 70, 90, 90]
    assert alert_collection.cycle(START)["status"] == "waiting"


def test_enqueue_race_reused_does_not_mark_or_process_alert(db, monkeypatch):
    saved()
    monkeypatch.setattr(search_jobs, "enqueue", lambda *args, **kwargs: {"reused": True, "id": "other"})
    monkeypatch.setattr(search_jobs, "process", lambda *args: (_ for _ in ()).throw(AssertionError("must not process")))
    assert alert_collection.cycle(START)["status"] == "waiting"
    with storage.connect() as conn:
        assert not conn.execute("SELECT 1 FROM runtime WHERE key='saved-search-collection:1'").fetchone()


def test_terminal_job_reconciles_after_scheduler_crash(db, monkeypatch):
    saved()
    queued = search_jobs.enqueue(1, {**storage.DEFAULT_PROFILE, "area_min": 70})
    alert_collection._save(1, {"job_id": queued["id"], "status": "pending", "last_attempt": START.isoformat(), "attempt_day": "2026-09-20"})
    monkeypatch.setattr(services, "refresh_source", lambda *args, **kwargs: {})
    search_jobs.process(1)
    assert alert_collection.cycle(START + timedelta(hours=4))["status"] == "waiting"


def test_partial_with_failed_source_retries_after_cooldown(db, monkeypatch):
    saved()
    def refresh(uid, sid, *, search_profile):
        if sid == 2:
            raise ValueError('source unavailable')
        return {'coverage': {'complete': True}}
    monkeypatch.setattr(services, 'refresh_source', refresh)
    assert alert_collection.cycle(START)['status'] == 'partial'
    assert alert_collection.cycle(START + timedelta(minutes=30))['status'] == 'waiting'
    assert alert_collection.cycle(START + timedelta(hours=1))['status'] == 'partial'
