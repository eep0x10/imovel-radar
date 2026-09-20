"""Collect saved-search snapshots independently of the account's current filters."""
from __future__ import annotations

import json
import os
from contextlib import closing
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import search_jobs, services, storage


def _key(search_id):
    return f"saved-search-collection:{search_id}"


def _save(search_id, state):
    with storage.transaction() as conn:
        conn.execute("INSERT INTO runtime VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (_key(search_id), storage.dumps(state)))


def _due(state, now, local, hour):
    if state.get("last_success_day") == local.date().isoformat():
        return False
    attempted = state.get("last_attempt")
    if attempted and now - datetime.fromisoformat(attempted) < timedelta(hours=1):
        return False
    # The first collection is immediate; retrying an initial failure also must
    # not wait for tomorrow's configured daily window.
    return not state.get("last_success_day") or local.hour >= hour


def cycle(now=None):
    """At most one due alert per invocation; all state survives worker restart."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(os.environ.get("IMOVEL_TIMEZONE", "America/Sao_Paulo"))
    hour = int(os.environ.get("IMOVEL_REFRESH_HOUR", "7"))
    if hour not in range(24):
        raise ValueError("IMOVEL_REFRESH_HOUR deve estar entre 0 e 23")
    local = now.astimezone(zone)
    owner = services.acquire_lock("saved-search-collection", minutes=2)
    if not owner:
        return {"status": "busy"}
    selected = None
    try:
        with closing(storage.connect()) as conn:
            rows = conn.execute("SELECT id,user_id,profile FROM saved_searches WHERE enabled=1 ORDER BY id").fetchall()
            states = {row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT key,value FROM runtime WHERE key LIKE 'saved-search-collection:%'")}
        for row in rows:
            state = states.get(_key(row["id"]), {})
            job = search_jobs.status(row["user_id"])
            # A crash after collection but before scheduling bookkeeping does
            # not cause another collection of the same successfully finished job.
            if job and state.get("job_id") == job["id"] and state.get("status") in search_jobs.ACTIVE and job["state"] not in search_jobs.ACTIVE:
                state["status"] = job["state"]
                if job["state"] in {"complete", "partial"} and not any(s.get("state") == "error" for s in job.get("sources", [])):
                    state["last_success_day"] = state["attempt_day"]
                    state["last_success"] = job.get("finished_at") or now.isoformat()
                _save(row["id"], state)
            if job and job["state"] in search_jobs.ACTIVE:
                continue
            if not _due(state, now, local, hour):
                continue
            # Recheck the current switch immediately before enqueueing. Source
            # enabled/authorized flags are snapshotted by enqueue and validated
            # again by refresh_source at execution time.
            with closing(storage.connect()) as conn:
                active = conn.execute("SELECT profile FROM saved_searches WHERE id=? AND user_id=? AND enabled=1", (row["id"], row["user_id"])).fetchone()
            if not active:
                continue
            queued = search_jobs.enqueue(row["user_id"], json.loads(active["profile"]), replace_active=False)
            if queued.get("reused"):
                continue
            state.update(last_attempt=now.isoformat(), attempt_day=local.date().isoformat(),
                         job_id=queued["id"], status=queued["state"])
            _save(row["id"], state)
            selected = (row, state, queued)
            break
    finally:
        services.release_lock("saved-search-collection", owner)
    if selected is None:
        return {"status": "waiting"}
    row, state, job = selected
    if job["state"] in search_jobs.ACTIVE:
        job = search_jobs.process(row["user_id"]) or job
    # Another worker may already own this exact job. Only a terminal result
    # belonging to the enqueued snapshot can mark this alert as collected.
    if job["id"] == state["job_id"]:
        state["status"] = job["state"]
        if job["state"] in {"complete", "partial"} and not any(s.get("state") == "error" for s in job.get("sources", [])):
            state["last_success_day"] = local.date().isoformat()
            state["last_success"] = now.isoformat()
        _save(row["id"], state)
    return {"status": job["state"], "search_id": row["id"], "job_id": state["job_id"]}
