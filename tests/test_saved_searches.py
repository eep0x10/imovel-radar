"""Saved-search baseline, isolation, lifecycle and frozen matching contracts."""
from tests.test_api import client, account, listing, commit
from app import storage


def search(client, headers, **changes):
    profile = client.get('/api/profile', headers=headers).json()
    response = client.post('/api/saved-searches', headers=headers,
                           json={'name': 'Minha busca', 'profile': profile, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def feed(client, headers, **params):
    return client.get('/api/notifications', headers=headers, params=params).json()


def test_baseline_new_dedupe_frozen_profile_and_export(client):
    a = account(client)
    commit(client, a, [listing()])
    saved = search(client, a)
    assert saved['baseline_count'] == 1
    assert feed(client, a)['total'] == 0
    profile = client.get('/api/profile', headers=a).json()
    client.put('/api/profile', headers=a, json={**profile, 'budget_max': 1})
    commit(client, a, [listing(external_id='new')])
    commit(client, a, [listing(external_id='new')])
    result = feed(client, a)
    assert result['total'] == result['unread'] == 1
    assert result['items'][0]['saved_search_id'] == saved['id']
    exported = client.get('/api/export', headers=a).json()
    assert len(exported['saved_searches']) == len(exported['notifications']) == 1


def test_pause_resume_isolation_and_read_all(client):
    a, b = account(client), account(client, 'bob')
    saved = search(client, a)
    assert client.patch(f"/api/saved-searches/{saved['id']}", headers=b, json={'enabled': False}).status_code == 404
    client.patch(f"/api/saved-searches/{saved['id']}", headers=a, json={'enabled': False})
    commit(client, a, [listing()])
    commit(client, b, [listing(external_id='private')])
    assert feed(client, a)['total'] == 0
    resumed = client.patch(f"/api/saved-searches/{saved['id']}", headers=a, json={'enabled': True}).json()
    assert resumed['notifications_created'] == 1
    assert client.patch(f"/api/saved-searches/{saved['id']}", headers=a, json={'enabled': True}).json()['notifications_created'] == 0
    assert feed(client, b)['total'] == 0
    assert client.get('/api/saved-searches', headers=b).json()['items'] == []
    assert client.patch('/api/notifications/read-all', headers=b).json()['updated'] == 0
    assert feed(client, a)['unread'] == 1
    assert client.patch('/api/notifications/read-all', headers=a).json()['updated'] == 1
    assert feed(client, a, unread_only=True)['total'] == 0


def test_text_phase_unknown_required_and_reentry(client):
    a = account(client)
    profile = client.get('/api/profile', headers=a).json()
    search(client, a, q='Mooca', construction='ready', profile={**profile, 'exclude_unknown_required': True, 'budget_max': 280000})
    commit(client, a, [listing(construction_status='ready')])
    assert feed(client, a)['total'] == 0
    commit(client, a, [listing(price=270000, construction_status='ready', observed_at='2026-09-19T12:00:00Z')])
    assert feed(client, a)['total'] == 1
    commit(client, a, [listing(price=310000, construction_status='ready', observed_at='2026-09-20T12:00:00Z')])
    commit(client, a, [listing(price=260000, construction_status='ready', observed_at='2026-09-21T12:00:00Z')])
    commit(client, a, [listing(external_id='other', neighborhood='Belem', construction_status='ready')])
    commit(client, a, [listing(external_id='phase', construction_status='off_plan')])
    commit(client, a, [listing(external_id='missing', construction_status='ready', metro_minutes=None)])
    assert feed(client, a)['total'] == 1


def test_canonical_dedupe_and_pagination(client):
    a = account(client)
    search(client, a)
    commit(client, a, [listing(address='Rua Teste, 100 apto 42')])
    commit(client, a, [listing(source='Other', external_id='copy', address='Rua Teste, 100 apto 42')])
    assert feed(client, a)['total'] == 1
    commit(client, a, [listing(external_id='second')])
    result = feed(client, a, page_size=1)
    assert result['total'] == 2 and result['has_more']
    assert len(feed(client, a, page=2, page_size=1)['items']) == 1


def test_account_validation_and_migration_idempotency(client):
    a = account(client)
    assert client.patch('/api/account', headers=a, json={'name': '  '}).status_code == 422
    assert client.patch('/api/account', headers=a, json={'name': 'Novo nome'}).json()['name'] == 'Novo nome'
    search(client, a)
    storage.initialize()
    storage.initialize()
    with storage.connect() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM saved_searches').fetchone()[0] == 1
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'



def test_purchase_with_tenant_preserved_rental_rejected(client):
    a = account(client)
    search(client, a)
    commit(client, a, [listing(external_id='tenant', title='Apartamento à venda com inquilino')])
    assert feed(client, a)['total'] == 1
    assert client.post('/api/properties', headers=a, json=listing(external_id='rental', title='Apartamento para alugar')).status_code == 422
    assert feed(client, a)['total'] == 1


def test_upgrade_v2_preserves_existing_rows(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv('IMOVEL_DB_PATH', str(tmp_path / 'v2.sqlite3'))
    with sqlite3.connect(storage.db_path()) as conn:
        conn.executescript(storage.SCHEMA)
        conn.execute('PRAGMA user_version=2')
        conn.execute('INSERT INTO users VALUES(1,?,?,?,?,?)', ('legacy@example.test', 'Legacy', 'not-a-secret', storage.dumps(storage.DEFAULT_PROFILE), storage.now_iso()))
        conn.execute("INSERT INTO alerts(user_id,kind,title,body,created_at,dedupe_key) VALUES(1,'new','Legacy','History',?,'legacy')", (storage.now_iso(),))
    storage.initialize()
    storage.initialize()
    with storage.connect() as conn:
        assert conn.execute('SELECT name FROM users').fetchone()[0] == 'Legacy'
        assert conn.execute('SELECT saved_search_id FROM alerts').fetchone()[0] is None
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
