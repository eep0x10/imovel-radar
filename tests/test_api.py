"""HTTP integration invariants against an isolated database and real lifespan."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import ingestion


PASSWORD = "test-only-strong-password"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("IMOVEL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("IMOVEL_ENABLE_LEGACY_IMPORT", raising=False)
    with TestClient(app) as session:
        yield session


def account(client, name="alice"):
    response = client.post("/api/auth/register", json={"email": f"{name}@example.com", "name": name, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def listing(**changes):
    return {**{"source": "Test source", "external_id": "apt-1", "url": "https://example.com/apt-1", "title": "Apartamento de teste", "price": 300000, "area": 50, "city": "São Paulo", "neighborhood": "Mooca", "property_type": "apartment", "bedrooms": 2, "parking": 0, "metro_minutes": 10, "condo_fee": 400, "property_tax": 1200, "tax_period": "annual", "status": "active", "observed_at": "2026-09-18T12:00:00Z"}, **changes}


def preview(client, headers, records):
    response = client.post("/api/import/preview", headers=headers, files={"file": ("listings.json", json.dumps(records).encode(), "application/json")})
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, headers, records):
    item = preview(client, headers, records)
    response = client.post("/api/import/commit", headers=headers, json={"preview_id": item["preview_id"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_lifecycle_and_private_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    for route in ("/api/properties", "/api/profile", "/api/export", "/api/alerts", "/api/sources", "/api/import/template.csv", "/api/status"):
        assert client.get(route).status_code == 401
    assert client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": "short"}).status_code == 422
    headers = account(client)
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "alice@example.com"
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong"}).status_code == 401
    login = client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert login.status_code == 200
    fresh = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_two_accounts_isolate_properties_tracking_alerts_and_export(client):
    alice, bob = account(client), account(client, "bob")
    a = client.post("/api/properties", headers=alice, json=listing()).json()
    b = client.post("/api/properties", headers=bob, json=listing(title="Bob private home")).json()
    assert a["id"] != b["id"]
    assert client.get("/api/properties", headers=bob).json()["total"] == 1
    assert client.get(f"/api/properties/{a['id']}", headers=bob).status_code == 404
    assert client.patch(f"/api/properties/{a['id']}/tracking", headers=bob, json={"saved": True}).status_code == 404
    tracking = {"saved": True, "stage": "visit", "notes": "Private negotiation notes", "visit_at": "2026-09-25T14:00:00-03:00", "checklist": {"documentation": True}}
    response = client.patch(f"/api/properties/{a['id']}/tracking", headers=alice, json=tracking)
    assert response.status_code == 200
    detail = client.get(f"/api/properties/{a['id']}", headers=alice).json()
    for key, value in tracking.items():
        assert detail[key] == value
    assert client.get("/api/properties?saved=true", headers=alice).json()["total"] == 1
    assert client.get("/api/properties?saved=true", headers=bob).json()["total"] == 0
    alerts = client.get("/api/alerts", headers=alice).json()
    assert alerts["unread"] == 1
    aid = alerts["items"][0]["id"]
    assert client.patch(f"/api/alerts/{aid}", headers=bob, json={"read": True}).status_code == 404
    assert client.patch(f"/api/alerts/{aid}", headers=alice, json={"read": True}).status_code == 200
    assert client.get("/api/alerts", headers=alice).json()["unread"] == 0
    exported = client.get("/api/export", headers=bob)
    assert exported.status_code == 200
    assert exported.json()["user"]["email"] == "bob@example.com"
    assert len(exported.json()["properties"]) == 1
    assert "Private negotiation" not in exported.text
    assert "alice@example.com" not in exported.text
    assert "password_hash" not in exported.text and "token_hash" not in exported.text


def test_preview_private_idempotent_and_reimport_does_not_duplicate(client):
    alice, bob = account(client), account(client, "bob")
    item = preview(client, alice, [listing()])
    assert item["valid"] == 1 and item["errors"] == []
    assert client.get("/api/properties", headers=alice).json()["total"] == 0
    body = {"preview_id": item["preview_id"]}
    assert client.post("/api/import/commit", headers=bob, json=body).status_code == 404
    first = client.post("/api/import/commit", headers=alice, json=body)
    second = client.post("/api/import/commit", headers=alice, json=body)
    assert first.json() == second.json()
    assert first.json()["created"] == 1
    repeat = commit(client, alice, [listing()])
    assert repeat["created"] == repeat["updated"] == 0
    assert repeat["unchanged"] == 1
    properties = client.get("/api/properties", headers=alice).json()
    assert properties["total"] == 1
    pid = properties["items"][0]["id"]
    assert len(client.get(f"/api/properties/{pid}", headers=alice).json()["history"]) == 1
    assert client.get("/api/alerts", headers=alice).json()["unread"] == 1


def test_import_with_any_invalid_row_is_atomic(client):
    headers = account(client)
    item = preview(client, headers, [listing(), listing(external_id="bad", price=-1)])
    assert item["errors"]
    assert client.post("/api/import/commit", headers=headers, json={"preview_id": item["preview_id"]}).status_code == 422
    assert client.get("/api/properties", headers=headers).json()["total"] == 0


def test_price_drop_history_alert_and_older_observation_cannot_revert(client):
    headers = account(client)
    commit(client, headers, [listing()])
    drop = listing(price=270000, observed_at="2026-09-19T12:00:00Z")
    assert commit(client, headers, [drop])["updated"] == 1
    assert commit(client, headers, [drop])["unchanged"] == 1
    assert commit(client, headers, [listing(price=320000)])["unchanged"] == 1
    assert commit(client, headers, [listing(price=320000, observed_at=None)])["unchanged"] == 1
    properties = client.get("/api/properties?drops=true", headers=headers).json()
    assert properties["total"] == 1
    item = properties["items"][0]
    assert item["price"] == 270000 and item["price_change"] == -30000
    detail = client.get(f"/api/properties/{item['id']}", headers=headers).json()
    assert [h["price"] for h in detail["history"]] == [300000, 270000]
    assert len([a for a in detail["alerts"] if a["kind"] == "price_drop"]) == 1


def test_profile_customization_isolated_and_budget_validated(client):
    alice, bob = account(client), account(client, "bob")
    client.post("/api/properties", headers=alice, json=listing())
    profile = client.get("/api/profile", headers=alice).json()
    profile.update(budget_max=200000, cities=[], neighborhoods=[], weights={"price": 90, "location": 5, "quality": 5})
    assert client.put("/api/profile", headers=alice, json=profile).json() == profile
    assert client.get("/api/profile", headers=bob).json()["budget_max"] == 330000
    assert client.get("/api/properties?apply_profile=true", headers=alice).json()["total"] == 0
    assert client.put("/api/profile", headers=alice, json={**profile, "area_min": 100, "area_max": 50}).status_code == 422
    budget = {"price": 300000, "down_payment": 60000, "annual_rate": 0, "months": 240, "model": "sac", "monthly_costs": 500}
    result = client.post("/api/budget", headers=alice, json=budget)
    assert result.status_code == 200
    assert result.json()["first_month_total"] == 1500
    assert result.json()["schedule"][-1]["balance"] == 0
    assert client.post("/api/budget", headers=alice, json={**budget, "down_payment": 400000}).status_code == 422


def test_feed_refresh_failure_preserves_snapshot_and_last_success(client, monkeypatch):
    alice, bob = account(client), account(client, "bob")
    source = {"name": "Authorized test feed", "url": "https://example.com/listings.json", "authorized": True}
    sid = client.post("/api/sources", headers=alice, json=source).json()["id"]
    assert client.post(f"/api/sources/{sid}/refresh", headers=bob).status_code == 404
    assert client.patch(f"/api/sources/{sid}", headers=bob, json={"enabled": False}).status_code == 404
    parsed = ingestion.parse_upload(json.dumps([listing()]).encode(), "fixture.json")
    monkeypatch.setattr(ingestion, "fetch_feed", lambda url: parsed)
    first = client.post(f"/api/sources/{sid}/refresh", headers=alice)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 1
    assert client.post(f"/api/sources/{sid}/refresh", headers=alice).json()["unchanged"] == 1
    before = client.get("/api/properties", headers=alice).json()["items"]
    healthy = next(s for s in client.get("/api/sources", headers=alice).json()["items"] if s["id"] == sid)
    assert healthy["status"] == "healthy" and healthy["last_success"]
    def failed(url):
        raise RuntimeError("upstream failed with private diagnostic")
    monkeypatch.setattr(ingestion, "fetch_feed", failed)
    failure = client.post(f"/api/sources/{sid}/refresh", headers=alice)
    assert failure.status_code in (422, 502)
    assert "private diagnostic" not in failure.text
    after = client.get("/api/properties", headers=alice).json()["items"]
    assert after == before
    unhealthy = next(s for s in client.get("/api/sources", headers=alice).json()["items"] if s["id"] == sid)
    assert unhealthy["status"] == "error"
    assert unhealthy["last_success"] == healthy["last_success"]
    assert unhealthy["last_attempt"] >= healthy["last_attempt"]
    monkeypatch.setattr(ingestion, "fetch_feed", lambda url: {"records": [], "errors": [], "warnings": []})
    assert client.post(f"/api/sources/{sid}/refresh", headers=alice).status_code in (422, 502)
    assert client.get("/api/properties", headers=alice).json()["items"] == before

def test_construction_filter_groups_plan_and_defaults_ready(client):
    headers = account(client)
    commit(client, headers, [
        listing(external_id='plan', title='Apartamento na planta'),
        listing(external_id='building', construction_status='under_construction'),
        listing(external_id='ready', title='Apartamento pronto para morar'),
        listing(external_id='unspecified', title='Apartamento com planta ampla'),
    ])
    for phase, expected in [('off_plan', {'plan','building'}), ('under_construction', {'plan','building'}), ('ready', {'ready','unspecified'}), ('unknown', {'ready','unspecified'})]:
        response = client.get('/api/properties', headers=headers, params={'construction': phase})
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert {p['external_id'] for p in response.json()['items']} == expected
    assert client.get('/api/properties', headers=headers).json()['total'] == 4
    assert client.get('/api/properties?construction=invalid', headers=headers).status_code == 422


def test_construction_does_not_guess_from_generic_or_negated_title():
    from app.construction import construction_status
    for title in ['Apartamento novo', 'Lançamento de oferta', 'Não é na planta', 'Planta com 2 quartos']:
        assert construction_status({'title': title}) == 'ready'
    assert construction_status({'title': 'Na planta', 'construction_status': 'ready'}) == 'ready'

@pytest.mark.parametrize('extra', [
    {'transaction_type': 'rent'}, {'business_context': 'RENT'},
    {'url': 'https://example.com/alugar/apartamento'},
    {'title': 'Apartamento para alugar'},
])
def test_rentals_rejected(client, extra):
    headers = account(client)
    result = preview(client, headers, [listing(**extra)])
    assert result['valid'] == 0
    assert result['errors']


def test_sale_with_tenant_remains_purchase(client):
    headers = account(client)
    result = preview(client, headers, [listing(title='Apartamento à venda com renda de aluguel')])
    assert result['valid'] == 1


def test_export_keeps_legacy_alert_history_separate(client):
    headers = account(client)
    commit(client, headers, [listing()])
    exported = client.get('/api/export', headers=headers).json()
    assert exported['historical_alerts']
    assert exported['notifications'] == []
    assert all(a['kind'] != 'saved_search_match' for a in exported['historical_alerts'])


def test_construction_description_and_unrelated_negation():
    from app.construction import construction_status
    assert construction_status({'description': 'Apartamento na planta, sem vaga'}) == 'under_construction'
    assert construction_status({'title': 'Sem vaga, em construção'}) == 'under_construction'
    assert construction_status({'construction_status': 'off_plan'}) == 'under_construction'
    assert construction_status({}) == 'ready'

def test_search_api_uses_submitted_profile_and_isolates_accounts(client, monkeypatch):
    from app import search_jobs
    a, b = account(client, 'search-a'), account(client, 'search-b')
    calls = []
    monkeypatch.setattr(search_jobs, 'drain', lambda uid: calls.append(uid))
    old = client.get('/api/profile', headers=a).json()
    response = client.post('/api/search', headers=a, json={**old, 'area_min': 70, 'area_max': None})
    assert response.status_code == 202
    assert response.json()['profile']['area_min'] == 70
    assert response.json()['state'] == 'error'  # No sources: never pretend success.
    assert client.get('/api/search', headers=b).json() is None
    assert client.get('/api/profile', headers=a).json() == old
    assert client.post('/api/search', headers=a, json={**old, 'area_min':100, 'area_max':70}).status_code == 422
    assert client.get('/api/search').status_code == 401
    assert len(calls) == 1
