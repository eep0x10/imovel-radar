from tests.test_api import client, account, listing
from app import portal_collectors, storage


def test_eight_character_password_and_portal_isolation(client, monkeypatch):
    registered = client.post('/api/auth/register', json={'email':'eight@example.com','name':'Eight','password':'abcdefgh'})
    assert registered.status_code == 201
    a = {'Authorization':'Bearer '+registered.json()['token']}
    b = account(client, 'other')
    catalog = client.get('/api/sources', headers=a).json()['catalog']
    assert {x['portal'] for x in catalog if x['supported']} == {'quintoandar','loft'}
    sid = client.post('/api/sources/portal', headers=a, json={'portal':'quintoandar'}).json()['id']
    assert client.post('/api/sources/portal', headers=a, json={'portal':'quintoandar'}).json()['id'] == sid
    assert client.post(f'/api/sources/{sid}/refresh', headers=b).status_code == 404
    assert client.patch(f'/api/sources/{sid}', headers=b, json={'enabled':False}).status_code == 404
    monkeypatch.setattr(portal_collectors, 'collect_portal', lambda *args: {'records':[listing()], 'errors':[], 'warnings':['Partial sample'], 'coverage':{'complete':False,'pages':1,'reason':'page_limit'}})
    result = client.post(f'/api/sources/{sid}/refresh', headers=a)
    assert result.status_code == 200, result.text
    assert result.json()['created'] == 1
    source = client.get('/api/sources', headers=a).json()['items'][0]
    assert source['status'] == 'partial'
    assert source['last_result']['coverage']['pages'] == 1
    assert client.get('/api/properties', headers=b).json()['total'] == 0
    monkeypatch.setattr(portal_collectors, 'collect_portal', lambda *args: {'records':[], 'errors':[{'message':'HTTP 403'}], 'warnings':[], 'coverage':{'complete':False}})
    assert client.post(f'/api/sources/{sid}/refresh', headers=a).status_code == 422
    assert client.get('/api/properties', headers=a).json()['total'] == 1
    assert client.patch(f'/api/sources/{sid}', headers=a, json={'enabled':False}).status_code == 200


def test_portal_zero_results_is_valid_and_worker_includes_portals(client, monkeypatch):
    from app.worker import cycle
    from datetime import datetime, timezone
    a = account(client)
    sid = client.post('/api/sources/portal', headers=a, json={'portal':'loft'}).json()['id']
    monkeypatch.setattr(portal_collectors, 'collect_portal', lambda *args: {'records':[], 'errors':[], 'warnings':[], 'coverage':{'complete':True,'pages':1,'reason':'exhausted','total_reported':0}})
    result = cycle(datetime(2026,9,20,12,tzinfo=timezone.utc), force=True)
    assert result['results'][0]['source_id'] == sid
    assert result['results'][0]['status'] == 'success'
    assert cycle(datetime(2026,9,20,13,tzinfo=timezone.utc), force=True)['results'] == []
