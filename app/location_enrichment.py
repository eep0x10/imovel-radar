"""Optional Google Maps walking-to-subway enrichment with a 30-day SQLite cache.

Only public listing addresses/coordinates are sent. No credentials or raw provider
errors are stored. Endpoints use the existing project's legacy Maps API contract.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import logging
from urllib.parse import quote
import os
import time

import httpx

from app import storage

BASE_URL = "https://maps.googleapis.com/maps/api/"
CACHE_DAYS = 30
STOP_STATUSES = {"REQUEST_DENIED", "OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"}


class ProviderFailure(Exception):
    def __init__(self, code: str, stop: bool = False):
        self.code = code
        self.stop = stop
        super().__init__(code)


@contextmanager
def _redacted_http_logging(api_key):
    class RedactKey(logging.Filter):
        def filter(self, record):
            message = record.getMessage()
            for secret in (api_key, quote(api_key, safe='')):
                message = message.replace(secret, '[REDACTED]')
            record.msg, record.args = message, ()
            return True
    redactor = RedactKey()
    loggers = [logging.getLogger(name) for name in ('httpx', 'httpcore.http11', 'httpcore.http2', 'httpcore.connection', 'httpcore.proxy')]
    for logger in loggers:
        logger.addFilter(redactor)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeFilter(redactor)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _coordinates(record):
    lat, lng = _number(record.get("latitude")), _number(record.get("longitude"))
    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


def _bounded_env(name, default, maximum):
    try:
        return max(0, min(maximum, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def _cache_key(record):
    coords = _coordinates(record)
    if coords:
        location = f"coordinates:{coords[0]:.6f},{coords[1]:.6f}"
    else:
        address = str(record.get("address") or "").strip()
        city = str(record.get("city") or "").strip()
        if not address or not city:
            return None, None
        location = ", ".join(filter(None, [address, str(record.get("neighborhood") or "").strip(), city, "Brasil"]))
    canonical = " ".join(location.casefold().split())
    return "metro-cache:v1:" + hashlib.sha256(canonical.encode()).hexdigest(), location


def _cache_read(key, now):
    with closing(storage.connect()) as conn:
        row = conn.execute("SELECT value FROM runtime WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    try:
        entry = json.loads(row[0])
        timestamp = datetime.fromisoformat(entry["checked_at"])
        if timestamp.tzinfo is None or not now - timedelta(days=CACHE_DAYS) <= timestamp <= now:
            return None
        if (_number(entry.get("metro_minutes")) is None or entry["metro_minutes"] < 0
                or _number(entry.get("metro_distance_meters")) is None
                or not isinstance(entry.get("metro_station"), str) or not entry["metro_station"]
                or not _coordinates(entry) or "coordinates_source" not in entry or "candidate_limit" not in entry):
            return None
        return entry
    except (ValueError, TypeError, KeyError):
        return None


def _cache_write(key, entry):
    with storage.transaction() as conn:
        conn.execute("INSERT INTO runtime(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, storage.dumps(entry)))


def _request(client, endpoint, params, api_key):
    try:
        response = client.get(BASE_URL + endpoint, params={**params, "key": api_key, "language": "pt-BR"})
        if response.status_code in (401, 403, 429):
            raise ProviderFailure("PROVIDER_ACCESS_LIMIT", stop=True)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        # Never stringify provider exceptions: their request URL can contain the key.
        raise ProviderFailure("PROVIDER_UNAVAILABLE") from None
    if not isinstance(body, dict):
        raise ProviderFailure("INVALID_RESPONSE")
    status = body.get("status")
    if status in STOP_STATUSES:
        raise ProviderFailure(str(status), stop=True)
    if status == "ZERO_RESULTS":
        return None
    if status != "OK":
        raise ProviderFailure("PROVIDER_UNAVAILABLE")
    return body


def _lookup(client, record, location, api_key, now, counter, deadline):
    def request(endpoint, params):
        if time.monotonic() >= deadline:
            raise ProviderFailure("TIME_BUDGET", stop=True)
        counter[0] += 1
        return _request(client, endpoint, params, api_key)

    coords = _coordinates(record)
    coordinates_source = "listing"
    if not coords:
        result = request("geocode/json", {"address": location, "region": "br"})
        if not result or not result.get("results"):
            raise ProviderFailure("NO_GEOCODE")
        candidates = result["results"]
        candidate = candidates[0]
        geometry = candidate.get("geometry") or {}
        # A neighborhood/street centroid is not a trustworthy walking origin.
        if candidate.get("partial_match") or geometry.get("location_type") not in {"ROOFTOP", "RANGE_INTERPOLATED"}:
            raise ProviderFailure("IMPRECISE_ADDRESS")
        point = geometry.get("location") or {}
        coords = _coordinates({"latitude": point.get("lat"), "longitude": point.get("lng")})
        if not coords:
            raise ProviderFailure("NO_GEOCODE")
        coordinates_source = "Google Maps"
    origin = f"{coords[0]},{coords[1]}"
    nearby = request("place/nearbysearch/json", {"location": origin, "rankby": "distance", "type": "subway_station"})
    if not nearby or not nearby.get("results"):
        raise ProviderFailure("NO_STATION")
    best = None
    limit = max(1, _bounded_env("IMOVEL_METRO_CANDIDATE_LIMIT", 3, 5))
    for station in nearby["results"][:limit]:
        if not isinstance(station, dict) or not station.get("place_id") or not station.get("name"):
            continue
        route = request("directions/json", {"origin": origin, "destination": "place_id:" + station["place_id"], "mode": "walking"})
        if not route or not route.get("routes"):
            continue
        legs = route["routes"][0].get("legs") or []
        if not legs:
            continue
        durations = [_number((leg.get("duration") or {}).get("value")) for leg in legs]
        distances = [_number((leg.get("distance") or {}).get("value")) for leg in legs]
        if any(v is None or v < 0 for v in durations + distances):
            continue
        duration, distance = sum(durations), sum(distances)
        if best is None or duration < best[0]:
            best = (duration, distance, station["name"])
    if best is None:
        raise ProviderFailure("NO_WALKING_ROUTE")
    return {"latitude": coords[0], "longitude": coords[1], "coordinates_source": coordinates_source,
            "metro_minutes": round(best[0] / 60, 2), "metro_distance_meters": round(best[1]),
            "metro_station": best[2], "checked_at": now.isoformat(), "candidate_limit": limit}


def _apply(record, entry):
    record["metro_minutes"] = entry["metro_minutes"]
    record["metro_station"] = entry["metro_station"]
    record["metro_distance_meters"] = entry["metro_distance_meters"]
    record["metro_checked_at"] = entry["checked_at"]
    record["metro_route_mode"] = "walking"
    record["metro_route_source"] = "Google Maps"
    record["metro_candidate_limit"] = entry["candidate_limit"]
    provenance = record.setdefault("provenance", {})
    for field in ("metro_minutes", "metro_station", "metro_distance_meters"):
        provenance[field] = {"source": "Google Maps", "observed_at": entry["checked_at"]}
    if not _coordinates(record):
        record["latitude"], record["longitude"] = entry["latitude"], entry["longitude"]
        for field in ("latitude", "longitude"):
            provenance[field] = {"source": entry["coordinates_source"], "observed_at": entry["checked_at"]}


def enrich_records(records, profile):
    """Return copied records, warnings and bounded lookup statistics; never raises API errors.

    Existing complete metro data stays untouched. Missing address/city or uncertain
    geocoding remains unknown. profile does not replace a missing listing address.
    Cache uses the application's SQLite runtime table, with atomic transactions.
    """
    output = [deepcopy(record) for record in records]
    result = {"records": output, "warnings": [], "enriched": 0, "cache_hits": 0, "lookups": 0, "requests": 0}
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        result["warnings"].append("Metrô: Google Maps não configurado; distâncias desconhecidas foram preservadas.")
        return result
    limit = _bounded_env("IMOVEL_GEOCODE_LIMIT", 20, 100)
    budget = max(1, _bounded_env("IMOVEL_GEOCODE_TIME_BUDGET", 60, 300))
    deadline, now, counter = time.monotonic() + budget, datetime.now(timezone.utc), [0]
    warnings = set()
    with _redacted_http_logging(api_key), httpx.Client(timeout=httpx.Timeout(8, connect=4), follow_redirects=False, trust_env=False) as client:
        for record in output:
            if _number(record.get("metro_minutes")) is not None and record.get("metro_station"):
                continue
            key, location = _cache_key(record)
            if not key:
                warnings.add("Metrô: anúncios sem endereço e cidade ou coordenadas permaneceram sem estimativa.")
                continue
            try:
                cached = _cache_read(key, now)
            except Exception:
                cached = None
                warnings.add("Metrô: cache indisponível; os dados da coleta foram preservados.")
            if cached:
                _apply(record, cached)
                result["cache_hits"] += 1
                result["enriched"] += 1
                continue
            if result["lookups"] >= limit:
                warnings.add(f"Metrô: limite de {limit} consultas de imóveis atingido nesta coleta; demais distâncias permanecem pendentes.")
                continue
            result["lookups"] += 1
            try:
                entry = _lookup(client, record, location, api_key, now, counter, deadline)
                _apply(record, entry)
                result["enriched"] += 1
                try:
                    _cache_write(key, entry)
                except Exception:
                    warnings.add("Metrô: resultado obtido, mas não foi possível armazenar o cache.")
            except ProviderFailure as exc:
                warnings.add({"NO_GEOCODE": "Metrô: endereço não localizado; distância permanece pendente.",
                              "IMPRECISE_ADDRESS": "Metrô: endereço impreciso; não foi estimado trajeto a partir do centro do bairro ou rua.",
                              "NO_STATION": "Metrô: nenhuma estação encontrada para alguns anúncios.",
                              "NO_WALKING_ROUTE": "Metrô: trajeto a pé não disponível para alguns anúncios.",
                              "TIME_BUDGET": "Metrô: tempo máximo de enriquecimento atingido; demais distâncias permanecem pendentes."
                              }.get(exc.code, "Metrô: serviço indisponível ou acesso limitado; distâncias desconhecidas foram preservadas."))
                if exc.stop:
                    break
            except (KeyError, TypeError, ValueError, IndexError):
                warnings.add("Metrô: resposta incompleta do serviço; distância permanece pendente.")
    result["requests"] = counter[0]
    result["warnings"] += sorted(warnings)
    return result
