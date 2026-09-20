"""Durable, account-scoped source searches with frozen filters and resumable progress."""
from __future__ import annotations

import json
import secrets
from contextlib import closing
from threading import Event, Thread

from . import services, storage

ACTIVE = {"pending", "running"}


def _key(user_id):
    return f"search-job:{int(user_id)}"


def _read(conn, user_id):
    row = conn.execute("SELECT value FROM runtime WHERE key=?", (_key(user_id),)).fetchone()
    return json.loads(row[0]) if row else None


def _write(conn, user_id, job, *, preserve_queue=True):
    if preserve_queue:
        current = _read(conn, user_id)
        if current and current["id"] == job["id"]:
            job["queued"] = bool(current.get("next_profile"))
            job["next_profile"] = current.get("next_profile")
    job["updated_at"] = storage.now_iso()
    conn.execute("INSERT INTO runtime(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (_key(user_id), storage.dumps(job)))


def status(user_id):
    """Return only this account's latest search; no provider payloads or URLs."""
    with closing(storage.connect()) as conn:
        return _read(conn, user_id)


def enqueue(user_id, profile, *, replace_active=True):
    """Atomically reuse an active job or capture a new exact filter/source snapshot."""
    from .schemas import Profile
    snapshot = Profile.model_validate(profile).model_dump()
    with storage.transaction() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise ValueError("Conta não encontrada")
        current = _read(conn, user_id)
        if current and current["state"] in ACTIVE:
            if not replace_active:
                return {**current, "reused": True}
            if current["profile"] == snapshot:
                # The latest intent is the running snapshot: cancel any older
                # queued request rather than surprisingly changing filters later.
                current.update(queued=False, next_profile=None)
                _write(conn, user_id, current, preserve_queue=False)
                return {**current, "reused": True}
            if current["state"] == "running":
                current.update(queued=True, next_profile=snapshot)
                _write(conn, user_id, current, preserve_queue=False)
                return {**current, "reused": True}
            # Pending jobs have not been claimed by a worker; replace atomically.
        job = _new_job(conn, user_id, snapshot)
        _write(conn, user_id, job, preserve_queue=False)
    return {**job, "reused": False}


def _new_job(conn, user_id, snapshot):
    sources = conn.execute("SELECT id,name FROM sources WHERE user_id=? AND enabled=1 AND authorized=1 AND kind IN ('portal','feed') ORDER BY id", (user_id,)).fetchall()
    now = storage.now_iso()
    return {"id": secrets.token_hex(16), "state": "pending" if sources else "error",
            "profile": snapshot, "created_at": now, "updated_at": now,
            "queued": False, "next_profile": None,
            "finished_at": None if sources else now, "completed": 0, "total": len(sources),
            "sources": [{"id": row["id"], "name": row["name"], "state": "pending"} for row in sources],
            "message": "Busca aguardando execução." if sources else "Nenhuma fonte habilitada e autorizada. Configure as fontes para pesquisar."}


def _summary(result):
    # Deliberate allow-list: collectors may attach raw provider diagnostics.
    summary = {"warnings_count": len(result.get("warnings") or [])}
    for key in ("inserted", "updated", "unchanged", "received", "created", "processed", "alerts"):
        value = result.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            summary[key] = value
    coverage = result.get("coverage")
    if isinstance(coverage, dict):
        summary["coverage"] = {key: value for key, value in coverage.items()
                               if key in {"complete", "pages", "total", "collected", "fetched", "total_available", "pages_fetched", "total_reported", "received", "retained", "excluded_known_filters"}
                               and isinstance(value, (bool, int, float))}
        if coverage.get("reason") in {"time_limit", "exhausted", "empty_page_before_total", "empty_page_unverified", "repeated_page", "error", "run_page_limit", "no_next_link", "page_limit"}:
            summary["coverage"]["reason"] = coverage["reason"]
    return summary


def process(user_id):
    """Process/resume one job. Safe to call concurrently from API and worker."""
    name = _key(user_id)
    owner = services.acquire_lock(name, minutes=10)
    if not owner:
        return status(user_id)
    stopped, lost = Event(), Event()

    def heartbeat():
        while not stopped.wait(30):
            try:
                if not services.renew_lock(name, owner, minutes=10):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with storage.transaction() as conn:
            job = _read(conn, user_id)
            if not job or job["state"] not in ACTIVE:
                return job
            job["state"] = "running"
            job.setdefault("started_at", storage.now_iso())
            _write(conn, user_id, job)
        for source in job["sources"]:
            if source["state"] in {"complete", "partial", "error"}:
                continue
            if lost.is_set() or not services.renew_lock(name, owner, minutes=10):
                return status(user_id)
            source["state"] = "running"
            job["message"] = f"Consultando {source['name']}…"
            with storage.transaction() as conn:
                _write(conn, user_id, job)
            try:
                result = services.refresh_source(user_id, source["id"], search_profile=job["profile"])
                source.update(_summary(result))
                source["state"] = "partial" if (result.get("coverage") or {}).get("complete") is False else "complete"
            except Exception:
                source["state"] = "error"
                source["message"] = "Não foi possível atualizar esta fonte. Os imóveis anteriores foram preservados; consulte o diagnóstico em Configurações."
            if lost.is_set():
                return status(user_id)
            source["finished_at"] = storage.now_iso()
            job["completed"] = sum(s["state"] in {"complete", "partial", "error"} for s in job["sources"])
            with storage.transaction() as conn:
                _write(conn, user_id, job)
        states = {s["state"] for s in job["sources"]}
        job["state"] = "error" if states == {"error"} else "partial" if states & {"error", "partial"} else "complete"
        job["message"] = {"error": "Nenhuma fonte pôde ser atualizada. Os resultados anteriores foram preservados.",
                          "partial": "Busca concluída parcialmente. Confira a cobertura de cada fonte.",
                          "complete": "Busca concluída. Os resultados disponíveis foram atualizados."}[job["state"]]
        job["finished_at"] = storage.now_iso()
        with storage.transaction() as conn:
            _write(conn, user_id, job)
            if job.get("next_profile"):
                replacement = _new_job(conn, user_id, job["next_profile"])
                _write(conn, user_id, replacement, preserve_queue=False)
        return job
    finally:
        stopped.set()
        thread.join(timeout=2)
        services.release_lock(name, owner)


def drain(user_id, max_jobs=3):
    """Start queued replacement filters promptly, with bounded work per invocation."""
    result = None
    for _ in range(max_jobs):
        result = process(user_id)
        current = status(user_id)
        if not result or not current or current['id'] == result['id'] or current['state'] not in ACTIVE:
            break
    return result


def process_pending():
    """Worker recovery also handles running jobs whose previous process exited."""
    with closing(storage.connect()) as conn:
        rows = conn.execute("SELECT key,value FROM runtime WHERE key LIKE 'search-job:%'").fetchall()
    results = []
    for row in rows:
        if json.loads(row["value"]).get("state") in ACTIVE:
            results.append(drain(int(row["key"].split(":", 1)[1])))
    return results
