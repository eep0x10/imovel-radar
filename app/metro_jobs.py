"""Walking routes are calculated only upon an explicit listing request."""
from datetime import datetime, timedelta, timezone
import json
import os
from . import storage
from .location_enrichment import _cache_key, enrich_records as google_enrich
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


def calculate(user_id, property_id):
    """Calculate and persist only the explicitly requested listing, never a batch."""
    from fastapi import HTTPException
    with storage.connect() as conn:
        row = conn.execute("SELECT data FROM properties WHERE id=? AND user_id=?", (property_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Imóvel não encontrado")
    lock = f"metro-property:{user_id}:{property_id}"
    owner = acquire_lock(lock, minutes=10)
    if not owner:
        raise HTTPException(409, "A rota deste imóvel já está sendo calculada. Aguarde e tente novamente.")
    try:
        with storage.connect() as conn:
            row = conn.execute("SELECT data FROM properties WHERE id=? AND user_id=?", (property_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, "Imóvel não encontrado")
        original = json.loads(row[0])
        if fresh(original):
            return {"property_id": property_id, **{key: original.get(key) for key in FIELDS}, "metro_status": "ready", "cached": True}
        record = json.loads(row[0])
        for key in FIELDS:
            record.pop(key, None)
        try:
            result = google_enrich([record], {})
            if os.getenv("IMOVEL_METRO_PROVIDER") != "osm":
                from .osm_walking import enrich_records
                result = enrich_records(result["records"], {})
            updated = result["records"][0]
        except Exception:
            updated = {"metro_status": "pending", "metro_message": "Não foi possível calcular a caminhada agora. Tente novamente pelo botão."}
        with storage.transaction() as conn:
            row = conn.execute("SELECT data FROM properties WHERE id=? AND user_id=?", (property_id, user_id)).fetchone()
            if not row:
                raise HTTPException(404, "Imóvel não encontrado")
            current = json.loads(row[0])
            if _cache_key(current)[0] != _cache_key(original)[0]:
                raise HTTPException(409, "A localização do imóvel mudou. Calcule a rota novamente.")
            for key in FIELDS:
                current.pop(key, None)
                if key in updated:
                    current[key] = updated[key]
            for key in ("latitude", "longitude"):
                if current.get(key) is None and updated.get(key) is not None:
                    current[key] = updated[key]
            provenance = current.setdefault("provenance", {})
            for key in FIELDS:
                provenance.pop(key, None)
            provenance.update({k: v for k, v in (updated.get("provenance") or {}).items() if k in FIELDS or k in ("latitude", "longitude")})
            if fresh(current):
                current["metro_status"] = "ready"
                current.pop("metro_message", None)
            else:
                current.setdefault("metro_status", "pending")
                current.setdefault("metro_message", "Caminhada não calculada. Confira a localização e tente novamente pelo botão.")
            conn.execute("UPDATE properties SET data=? WHERE id=? AND user_id=?", (storage.dumps(current), property_id, user_id))
        return {"property_id": property_id, **{key: current.get(key) for key in FIELDS}, "cached": False}
    finally:
        release_lock(lock, owner)
