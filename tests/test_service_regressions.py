"""Regressions found in the service audit; no public network or real account data."""
import json
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app import ingestion, storage
from app.main import app
from app.services import ingest, enrich_all


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('IMOVEL_DB_PATH', str(tmp_path / 'regression.sqlite3'))
    monkeypatch.delenv('IMOVEL_ENABLE_LEGACY_IMPORT', raising=False)
    storage.initialize()
    with storage.transaction() as conn:
        conn.execute('INSERT INTO users(email,name,password_hash,profile,created_at) VALUES(?,?,?,?,?)',
                     ('service@example.com', 'Service', 'unused', storage.dumps(storage.DEFAULT_PROFILE), storage.now_iso()))
    return tmp_path


def record(**changes):
    payload = {'source': 'Test', 'external_id': '1', 'price': 300000, 'area': 50, **changes}
    result = ingestion.parse_upload(json.dumps([payload]).encode(), 'test.json')
    assert not result['errors']
    return result['records'][0]


@pytest.mark.parametrize('field,prefix', [('external_id', 'x' * 256), ('source', 'x' * 100)])
def test_long_distinct_identity_preserved(database, field, prefix):
    records = [record(**{field: prefix + suffix}) for suffix in ('a', 'b')]
    with storage.transaction() as conn:
        result = ingest(conn, 1, records)
        assert result['created'] == 2 and result['updated'] == 0
        saved = enrich_all(conn, 1)
        assert {r[field] for r in saved} == {prefix + 'a', prefix + 'b'}
        assert ingest(conn, 1, records)['unchanged'] == 2


def test_timestamp_offsets_compared_as_instants(database):
    older = record(observed_at='2026-09-19T10:00:00+00:00')
    newer = record(observed_at='2026-09-19T08:00:00-03:00', price=270000)
    with storage.transaction() as conn:
        assert ingest(conn, 1, [older])['created'] == 1
        assert ingest(conn, 1, [newer])['updated'] == 1
        assert ingest(conn, 1, [older])['unchanged'] == 1
        current = enrich_all(conn, 1)[0]
        assert current['price'] == 270000
        assert current['observed_at'] == newer['observed_at']
        assert conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 2


def test_undated_price_reversion_keeps_event_and_consecutive_idempotency(database):
    with storage.transaction() as conn:
        for price in (300000, 270000, 300000, 270000):
            row = record(price=price)
            ingest(conn, 1, [row])
            assert ingest(conn, 1, [row])['unchanged'] == 1
        prices = [r[0] for r in conn.execute('SELECT price FROM observations ORDER BY id')]
        assert prices == [300000, 270000, 300000, 270000]
        current = enrich_all(conn, 1)[0]
        assert current['price_change'] == -30000
        assert conn.execute("SELECT COUNT(*) FROM alerts WHERE kind='price_drop'").fetchone()[0] == 2


def account(client, name):
    response = client.post('/api/auth/register', json={'email': name + '@example.com', 'name': name, 'password': 'strong-test-password-123'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_aggregated_feed_keeps_sources_and_repeat_refresh_is_idempotent(database, monkeypatch):
    monkeypatch.setattr(ingestion, 'fetch_feed', lambda _: {
        'records': [record(source='Loft', price=300000), record(source='QuintoAndar', price=310000)],
        'errors': [], 'warnings': []})
    with TestClient(app) as client:
        headers = account(client, 'feeds')
        source = client.post('/api/sources', headers=headers, json={'name': 'Authorized combined feed', 'url': 'https://example.com/feed', 'authorized': True})
        assert source.status_code == 201, source.text
        path = '/api/sources/' + str(source.json()['id']) + '/refresh'
        first = client.post(path, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()['created'] == 2
        second = client.post(path, headers=headers)
        assert second.status_code == 200 and second.json()['unchanged'] == 2
        items = client.get('/api/properties', headers=headers).json()['items']
        assert len(items) == 2
        assert {p['source'] for p in items} == {'Loft', 'QuintoAndar'}
        assert {p['price'] for p in items} == {300000, 310000}
        for item in items:
            detail = client.get('/api/properties/' + str(item['id']), headers=headers).json()
            assert len(detail['history']) == 1


def test_legacy_preview_is_owner_only_and_disabled_by_default(tmp_path, monkeypatch):
    from openpyxl import Workbook
    monkeypatch.setenv('IMOVEL_DB_PATH', str(tmp_path / 'legacy.sqlite3'))
    monkeypatch.setattr(storage, 'ROOT', tmp_path)
    monkeypatch.delenv('IMOVEL_ENABLE_LEGACY_IMPORT', raising=False)
    workbook = Workbook()
    workbook.active.append(['source', 'external_id', 'price', 'area'])
    workbook.active.append(['Private', 'owner-record', 300000, 50])
    workbook.save(tmp_path / 'resultados_quintoandar.xlsx')
    with TestClient(app) as client:
        owner = account(client, 'owner')
        other = account(client, 'other')
        route = '/api/import/legacy-preview'
        assert client.post(route, headers=owner).status_code == 404
        monkeypatch.setenv('IMOVEL_ENABLE_LEGACY_IMPORT', '1')
        assert client.post(route).status_code == 401
        assert client.post(route, headers=other).status_code == 404
        accepted = client.post(route, headers=owner)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()['valid'] == 1
        assert accepted.json()['records'][0]['external_id'] == 'owner-record'
        assert client.post('/api/import/commit', headers=other, json={'preview_id': accepted.json()['preview_id']}).status_code == 404
    with closing(storage.connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM previews WHERE user_id=2').fetchone()[0] == 0
