from datetime import datetime, timedelta, timezone
import json
import logging

import httpx
import pytest

from app import storage
from app import location_enrichment as loc

BASE = {"address": "Rua Exemplo, 100", "city": "São Paulo", "neighborhood": "Belém", "metro_minutes": None, "metro_station": None}
REAL_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("IMOVEL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-only-fake-key")
    monkeypatch.setenv("IMOVEL_GEOCODE_LIMIT", "20")
    monkeypatch.setenv("IMOVEL_METRO_CANDIDATE_LIMIT", "3")
    storage.initialize()


def mock_google(monkeypatch, handler):
    calls = []
    def transport(request):
        calls.append(request)
        return handler(request)
    monkeypatch.setattr(loc.httpx, "Client", lambda **kwargs: REAL_CLIENT(transport=httpx.MockTransport(transport), **kwargs))
    return calls


def ok_response(request):
    if "geocode" in request.url.path:
        return httpx.Response(200, json={"status": "OK", "results": [{"geometry": {"location_type": "ROOFTOP", "location": {"lat": -23.54, "lng": -46.58}}}]})
    if "nearbysearch" in request.url.path:
        assert request.url.params["rankby"] == "distance"
        assert "radius" not in request.url.params
        assert request.url.params["type"] == "subway_station"
        return httpx.Response(200, json={"status": "OK", "results": [{"name": "Belém", "place_id": "station1"}]})
    assert request.url.params["mode"] == "walking"
    return httpx.Response(200, json={"status": "OK", "routes": [{"legs": [{"duration": {"value": 615}, "distance": {"value": 802}}]}]})


def test_no_key_no_requests_and_original_preserved(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY")
    monkeypatch.setattr(loc.httpx, "Client", lambda **k: pytest.fail("Unexpected network client"))
    original = dict(BASE)
    r = loc.enrich_records([original], {})
    assert r["records"] == [original] and r["records"][0] is not original
    assert r["requests"] == 0 and r["warnings"]


def test_real_duration_seconds_cache_and_provenance(monkeypatch):
    calls = mock_google(monkeypatch, ok_response)
    r = loc.enrich_records([BASE, BASE], {})
    p = r["records"][0]
    assert p["metro_minutes"] == 10.25
    assert p["metro_station"] == "Belém" and p["metro_distance_meters"] == 802
    assert p["provenance"]["metro_minutes"]["source"] == "Google Maps"
    assert p.get("observed_at") is None
    assert len(calls) == 3 and r["cache_hits"] == 1
    assert BASE["metro_minutes"] is None
    assert loc.enrich_records([BASE], {})["cache_hits"] == 1
    assert len(calls) == 3


def test_stops_immediately_on_denied_without_leaking_key(monkeypatch, caplog):
    key = "test-only-fake-key"
    calls = mock_google(monkeypatch, lambda request: httpx.Response(200, json={"status": "REQUEST_DENIED", "error_message": key}))
    with caplog.at_level(logging.INFO, logger="httpx"):
        r = loc.enrich_records([BASE, {**BASE, "address": "Rua Segunda, 100"}], {})
    assert len(calls) == 1 and r["enriched"] == 0
    assert key not in json.dumps(r) and key not in caplog.text
    assert r["records"][0]["metro_minutes"] is None


@pytest.mark.parametrize("status", ["OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"])
def test_quota_stops(monkeypatch, status):
    calls = mock_google(monkeypatch, lambda request: httpx.Response(200, json={"status": status}))
    r = loc.enrich_records([BASE, {**BASE, "address": "Outra, 8"}], {})
    assert len(calls) == 1 and r["warnings"]


def test_limit_zero_and_missing_address_do_not_query(monkeypatch):
    monkeypatch.setenv("IMOVEL_GEOCODE_LIMIT", "0")
    calls = mock_google(monkeypatch, ok_response)
    r = loc.enrich_records([BASE, {"city": "São Paulo"}], {})
    assert not calls and r["warnings"] and r["enriched"] == 0


def test_limit_counts_uncached_records_only(monkeypatch):
    monkeypatch.setenv("IMOVEL_GEOCODE_LIMIT", "1")
    calls = mock_google(monkeypatch, ok_response)
    r = loc.enrich_records([BASE, BASE, {**BASE, "address": "Outra, 9"}], {})
    assert len(calls) == 3 and r["enriched"] == 2 and r["lookups"] == 1
    assert r["records"][2]["metro_minutes"] is None


def test_coordinates_skip_geocode_and_existing_complete_data_preserved(monkeypatch):
    calls = mock_google(monkeypatch, ok_response)
    known = {**BASE, "metro_minutes": 4, "metro_station": "Sé"}
    coords = {**BASE, "latitude": -23.5, "longitude": -46.5}
    r = loc.enrich_records([known, coords], {})
    assert r["records"][0] == known
    assert len(calls) == 2 and r["records"][1]["latitude"] == -23.5


def test_imprecise_geocoding_never_estimates_neighborhood_walk(monkeypatch):
    calls = mock_google(monkeypatch, lambda request: httpx.Response(200, json={"status": "OK", "results": [{"geometry": {"location_type": "APPROXIMATE", "location": {"lat": -23.5, "lng": -46.5}}}]}))
    r = loc.enrich_records([BASE], {})
    assert len(calls) == 1 and r["records"][0]["metro_minutes"] is None
    assert "impreciso" in r["warnings"][0]


def test_timeout_error_does_not_expose_request_or_key(monkeypatch):
    def error(request):
        raise httpx.ReadTimeout(str(request.url), request=request)
    mock_google(monkeypatch, error)
    r = loc.enrich_records([BASE], {})
    assert r["warnings"] and "test-only-fake-key" not in json.dumps(r)


def test_cache_expires_after_thirty_days(monkeypatch):
    calls = mock_google(monkeypatch, ok_response)
    loc.enrich_records([BASE], {})
    key, _ = loc._cache_key(BASE)
    with storage.transaction() as conn:
        entry = json.loads(conn.execute("SELECT value FROM runtime WHERE key=?", (key,)).fetchone()[0])
        entry["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        conn.execute("UPDATE runtime SET value=? WHERE key=?", (json.dumps(entry), key))
    r = loc.enrich_records([BASE], {})
    assert len(calls) == 6 and r["cache_hits"] == 0


def test_zero_results_keeps_unknown(monkeypatch):
    mock_google(monkeypatch, lambda request: httpx.Response(200, json={"status": "ZERO_RESULTS"}))
    r = loc.enrich_records([BASE], {})
    assert r["records"][0]["metro_minutes"] is None and r["warnings"]

def test_selects_fastest_real_walking_route_not_first_station(monkeypatch):
    def response(request):
        if "nearbysearch" in request.url.path:
            return httpx.Response(200, json={"status": "OK", "results": [{"name": "Primeira", "place_id": "first"}, {"name": "Segunda", "place_id": "second"}]})
        if "directions" in request.url.path:
            seconds = 900 if request.url.params["destination"] == "place_id:first" else 420
            return httpx.Response(200, json={"status": "OK", "routes": [{"legs": [{"duration": {"value": seconds}, "distance": {"value": 500}}]}]})
        return ok_response(request)
    calls = mock_google(monkeypatch, response)
    r = loc.enrich_records([BASE], {})
    assert r["records"][0]["metro_station"] == "Segunda"
    assert r["records"][0]["metro_minutes"] == 7
    assert len(calls) == 4


def test_malformed_route_does_not_invent_minutes(monkeypatch):
    def response(request):
        if "directions" in request.url.path:
            return httpx.Response(200, json={"status": "OK", "routes": [{"legs": [{"duration": {"value": "NaN"}, "distance": {"value": 500}}]}]})
        return ok_response(request)
    mock_google(monkeypatch, response)
    r = loc.enrich_records([BASE], {})
    assert r["records"][0]["metro_minutes"] is None and r["warnings"]
