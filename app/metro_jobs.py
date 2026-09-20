"""Resume missing walking routes independently of property recollection."""
from datetime import datetime, timedelta, timezone
import json
import os
from .sale_scope import rental_listing
from . import storage
from .location_enrichment import _cache_key, _coordinates, enrich_records as google_enrich
from .services import acquire_lock, release_lock

FIELDS = ("metro_minutes", "metro_station", "metro_distance_meters", "metro_checked_at", "metro_route_mode", "metro_route_source", "metro_candidate_limit", "metro_status", "metro_message", "metro_candidate_station", "metro_station_coverage")


def fresh(record, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        at = datetime.fromisoformat(record.get("metro_checked_at") or "")
        return (record.get("metro_minutes") is not None and bool(record.get("metro_station"))
                and at.tzinfo is not None and now - timedelta(days=30) <= at <= now)
    except (TypeError, ValueError):
        return False


def preserve_route(record, previous):
    if previous and fresh(previous) and _cache_key(record)[0] is not None and _cache_key(record)[0] == _cache_key(previous)[0] and record.get("metro_minutes") is None:
        for key in FIELDS:
            if key in previous:
                record[key] = previous[key]
        provenance = record.setdefault("provenance", {})
        for key in ("metro_minutes", "metro_station", "metro_distance_meters"):
            if key in (previous.get("provenance") or {}):
                provenance[key] = previous["provenance"][key]


def cycle(limit=3):
    owner = acquire_lock("metro-enrichment", minutes=10)
    if not owner:
        return {"status": "busy", "enriched": 0}
    try:
        now = datetime.now(timezone.utc)
        with storage.connect() as conn:
            rows = conn.execute("SELECT id,user_id,data FROM properties ORDER BY id DESC").fetchall()
            attempts = {row[0]: row[1] for row in conn.execute("SELECT key,value FROM runtime WHERE key LIKE 'metro-retry:%'")}
        candidates = []
        for row in rows:
            record = json.loads(row["data"])
            if rental_listing(record) or fresh(record) or record.get("status") in ("sold", "inactive", "unavailable"):
                continue
            previous = attempts.get(f"metro-retry:{row['id']}")
            if previous and previous > now.isoformat():
                continue
            candidates.append((previous or "", row, record))
        candidates.sort(key=lambda entry: (entry[0], _coordinates(entry[2]) is None))
        chosen = candidates[:max(1,min(20,limit))]
        if not chosen:
            return {"status": "waiting", "enriched": 0}
        records = [dict(item[2]) for item in chosen]
        for record in records:
            if record.get("metro_checked_at") and not fresh(record):
                for key in FIELDS:
                    record.pop(key, None)
        result = google_enrich(records, {})
        from .osm_walking import enrich_records
        if os.getenv("IMOVEL_METRO_PROVIDER") != "osm":
            result = enrich_records(result["records"], {})
        enriched = 0
        with storage.transaction() as conn:
            for (_, row, original), updated in zip(chosen, result["records"]):
                current_row = conn.execute("SELECT data FROM properties WHERE id=? AND user_id=?", (row["id"],row["user_id"])).fetchone()
                if not current_row:
                    continue
                current = json.loads(current_row[0])
                if _cache_key(current)[0] != _cache_key(original)[0]:
                    continue
                if current.get("metro_checked_at") and not fresh(current):
                    for key in FIELDS:
                        current.pop(key, None)
                for key in FIELDS:
                    if key in updated:
                        current[key] = updated[key]
                for key in ("latitude", "longitude"):
                    if current.get(key) is None and updated.get(key) is not None:
                        current[key] = updated[key]
                current.setdefault("provenance", {}).update({k:v for k,v in (updated.get("provenance") or {}).items() if k in FIELDS or k in ("latitude","longitude")})
                if fresh(current):
                    current["metro_status"] = "ready"
                    current.pop("metro_message", None)
                    enriched += 1
                else:
                    current.setdefault("metro_status", "pending")
                    current.setdefault("metro_message", "Caminhada pendente; aguardando localização precisa ou serviço de rotas.")
                conn.execute("UPDATE properties SET data=? WHERE id=? AND user_id=?", (storage.dumps(current),row["id"],row["user_id"]))
                retry = now + (timedelta(days=1) if current.get("metro_status") in ("coordinates_missing", "daily_limit", "ready") else timedelta(minutes=15))
                conn.execute("INSERT INTO runtime(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (f"metro-retry:{row['id']}",retry.isoformat()))
        return {"status": "completed", "enriched": enriched, "processed":len(chosen), "warnings":result.get("warnings",[])}
    finally:
        release_lock("metro-enrichment", owner)
