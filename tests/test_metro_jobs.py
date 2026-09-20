from datetime import datetime,timezone,timedelta
import json
from app import storage,metro_jobs


def test_preserve_route_only_when_current_location_and_cache_match():
    old={"latitude":-23.5,"longitude":-46.6,"metro_minutes":10,"metro_station":"Sé","metro_checked_at":datetime.now(timezone.utc).isoformat(),"metro_route_source":"OSM"}
    new={"latitude":-23.5,"longitude":-46.6,"metro_minutes":None}
    metro_jobs.preserve_route(new,old)
    assert new["metro_minutes"]==10
    moved={"latitude":-23.6,"longitude":-46.6}
    metro_jobs.preserve_route(moved,old)
    assert moved.get("metro_minutes") is None
    old["metro_checked_at"]=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    assert not metro_jobs.fresh(old)


from tests.test_api import client, account, listing
from app import location_enrichment, portal_collectors


def test_requested_route_is_private_scoped_and_cached(client, monkeypatch):
    a, b = account(client), account(client, "bob")
    first = client.post('/api/properties', headers=a, json=listing(latitude=-23.5, longitude=-46.6, metro_minutes=None)).json()['id']
    second = client.post('/api/properties', headers=a, json=listing(external_id="other", latitude=-23.5, longitude=-46.6, metro_minutes=None)).json()['id']
    calls = []
    monkeypatch.setenv('IMOVEL_METRO_PROVIDER', 'osm')
    def routed(records, profile):
        calls.append(records)
        return {'records': [{**records[0], 'metro_minutes': 12, 'metro_station': 'Belém', 'metro_checked_at': storage.now_iso()}]}
    monkeypatch.setattr(metro_jobs, 'google_enrich', routed)
    assert client.post(f'/api/properties/{first}/metro').status_code == 401
    assert client.post(f'/api/properties/{first}/metro', headers=b).status_code == 404
    assert not calls
    with storage.connect() as conn:
        before = conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        unchanged = conn.execute('SELECT data FROM properties WHERE id=?', (second,)).fetchone()[0]
    response = client.post(f'/api/properties/{first}/metro', headers=a)
    assert response.status_code == 200, response.text
    assert response.json()['metro_minutes'] == 12
    assert response.json()['metro_status'] == 'ready'
    assert client.post(f'/api/properties/{first}/metro', headers=a).json()['cached'] is True
    assert len(calls) == 1 and len(calls[0]) == 1
    with storage.connect() as conn:
        assert conn.execute('SELECT data FROM properties WHERE id=?', (second,)).fetchone()[0] == unchanged
        assert conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == before
        assert json.loads(conn.execute('SELECT data FROM properties WHERE id=?', (first,)).fetchone()[0])['price'] == 300000


def test_route_lock_and_location_change(client, monkeypatch):
    from app.services import acquire_lock, release_lock
    a = account(client)
    pid = client.post('/api/properties', headers=a, json=listing(latitude=-23.5, longitude=-46.6, metro_minutes=None)).json()['id']
    owner = acquire_lock(f'metro-property:1:{pid}', minutes=10)
    assert client.post(f'/api/properties/{pid}/metro', headers=a).status_code == 409
    release_lock(f'metro-property:1:{pid}', owner)
    monkeypatch.setenv('IMOVEL_METRO_PROVIDER', 'osm')
    def moved(records, profile):
        with storage.transaction() as conn:
            data = json.loads(conn.execute('SELECT data FROM properties WHERE id=?', (pid,)).fetchone()[0])
            data['latitude'] = -23.6
            conn.execute('UPDATE properties SET data=? WHERE id=?', (storage.dumps(data), pid))
        return {'records': [{**records[0], 'metro_minutes': 12, 'metro_station': 'Belém', 'metro_checked_at': storage.now_iso()}]}
    monkeypatch.setattr(metro_jobs, 'google_enrich', moved)
    assert client.post(f'/api/properties/{pid}/metro', headers=a).status_code == 409
    with storage.connect() as conn:
        data = json.loads(conn.execute('SELECT data FROM properties WHERE id=?', (pid,)).fetchone()[0])
        assert data['latitude'] == -23.6 and data.get('metro_minutes') is None


def test_source_refresh_never_calculates_routes(client, monkeypatch):
    a = account(client)
    sid = client.post('/api/sources/portal', headers=a, json={'portal': 'loft'}).json()['id']
    monkeypatch.setattr(portal_collectors, 'collect_portal', lambda *a: {'records': [listing(metro_minutes=None)], 'errors': [], 'warnings': [], 'coverage': {'complete': True}})
    def forbidden(*args):
        raise AssertionError('Route provider must not be called by collection')
    monkeypatch.setattr(location_enrichment, 'enrich_records', forbidden)
    assert client.post(f'/api/sources/{sid}/refresh', headers=a).status_code == 200


def test_failed_route_is_retryable_only_by_explicit_request(client, monkeypatch):
    a = account(client)
    pid = client.post('/api/properties', headers=a, json=listing(metro_minutes=None)).json()['id']
    def unavailable(*args):
        raise RuntimeError('upstream secret response')
    monkeypatch.setattr(metro_jobs, 'google_enrich', unavailable)
    response = client.post(f'/api/properties/{pid}/metro', headers=a)
    assert response.status_code == 200
    assert response.json()['metro_status'] == 'pending'
    assert response.json()['metro_minutes'] is None
    assert 'secret' not in response.text
    with storage.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM runtime WHERE key LIKE 'metro-retry:%'").fetchone()[0] == 0
    # The failure releases its lock, allowing the user to explicitly retry.
    assert client.post(f'/api/properties/{pid}/metro', headers=a).status_code == 200
