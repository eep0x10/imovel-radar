"""Daily, idempotent feed refresh with cross-process leases and visible heartbeat."""
from __future__ import annotations

import argparse
import logging
import os
import time
from threading import Event, Thread
from contextlib import closing
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import storage
from .services import acquire_lock, refresh_source, release_lock, renew_lock

log = logging.getLogger("radar.worker")


def cycle(now=None, force=False, touch_heartbeat=False):
    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo(os.environ.get("IMOVEL_TIMEZONE", "America/Sao_Paulo"))
    hour = int(os.environ.get("IMOVEL_REFRESH_HOUR", "7"))
    if hour not in range(24):
        raise ValueError("IMOVEL_REFRESH_HOUR deve estar entre 0 e 23")
    local = now.astimezone(zone)
    if not force and local.hour < hour:
        return {"status": "waiting", "results": []}
    owner = acquire_lock("daily-cycle", minutes=15)
    if not owner:
        return {"status": "busy", "results": []}
    results = []
    try:
        day = local.date().isoformat()
        with closing(storage.connect()) as conn:
            rows = conn.execute("SELECT * FROM sources WHERE kind IN ('feed','portal') AND enabled=1 AND authorized=1").fetchall()
        for source in rows:
            if not renew_lock("daily-cycle", owner):
                return {"status": "lease_lost", "results": results}
            if touch_heartbeat:
                heartbeat()
            with closing(storage.connect()) as conn:
                existing = conn.execute("SELECT status FROM daily_runs WHERE source_id=? AND day=?", (source["id"], day)).fetchone()
            if existing and existing[0] == "success":
                continue
            if not force and source["status"] == "error" and source["last_attempt"] and source["last_attempt"] > (now - timedelta(hours=1)).isoformat():
                continue
            try:
                summary = refresh_source(source["user_id"], source["id"])
                status = "success"
                results.append({"source_id": source["id"], "status": status, "summary": summary})
            except ValueError:
                status = "failed"
                results.append({"source_id": source["id"], "status": status})
            with storage.transaction() as conn:
                conn.execute("INSERT INTO daily_runs VALUES(?,?,?) ON CONFLICT(source_id,day) DO UPDATE SET status=excluded.status", (source["id"], day, status))
        with storage.transaction() as conn:
            conn.execute("INSERT INTO runtime VALUES('worker_last_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (storage.now_iso(),))
        return {"status": "completed", "results": results}
    finally:
        release_lock("daily-cycle", owner)


def heartbeat():
    with storage.transaction() as conn:
        conn.execute("INSERT INTO runtime VALUES('worker_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (storage.now_iso(),))


def main():
    parser = argparse.ArgumentParser(description="Atualização diária dos feeds autorizados")
    parser.add_argument("--once", action="store_true", help="Executar um ciclo e sair")
    parser.add_argument("--force", action="store_true", help="Ignorar apenas horário e cooldown; preserva idempotência diária")
    args = parser.parse_args()
    storage.initialize()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        result = cycle(force=args.force)
        log.info("cycle=%s sources=%d", result["status"], len(result["results"]))
        return
    stopped = Event()
    def keep_alive():
        while not stopped.wait(30):
            try:
                heartbeat()
            except Exception:
                log.warning("Worker heartbeat temporarily unavailable")
    Thread(target=keep_alive, daemon=True).start()
    while True:
        try:
            heartbeat()
            from . import search_jobs, alert_collection
            search_jobs.process_pending()
            alert_collection.cycle()
            result = cycle(touch_heartbeat=True)
            if result["results"]:
                log.info("cycle=%s sources=%d", result["status"], len(result["results"]))
        except Exception:
            log.error("Worker cycle failed; stored listings retained. Check configuration and database.")
        time.sleep(60)


if __name__ == "__main__":
    main()
