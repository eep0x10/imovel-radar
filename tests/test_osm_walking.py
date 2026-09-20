import httpx
import pytest
from app import osm_walking as osm, storage

REAL_CLIENT = httpx.Client

@pytest.fixture(autouse=True)
def db(monkeypatch, tmp_path):
    monkeypatch.setenv('IMOVEL_DB_PATH', str(tmp_path/'test.sqlite3'))
    storage.initialize()
    monkeypatch.setattr(osm.time, 'sleep', lambda _: None)


def test_route_best_is_duration_not_straight_line_and_cached(monkeypatch):
    osm._write('stations', {'at': osm.time.time(), 'items': [dict(name=str(i), latitude=-23.55, longitude=-46.63-i/100) for i in range(3)]})
    monkeypatch.setattr(osm, '_reserve', lambda kind: None)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'code':'Ok','routes':[{'duration':[600,300,450][len(calls)-1],'distance':700}]})
    monkeypatch.setattr(osm.httpx, 'Client', lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))
    item=dict(latitude=-23.55,longitude=-46.63)
    result=osm.enrich_records([item])
    assert result['records'][0]['metro_minutes']==5
    assert result['records'][0]['metro_station']=='1'
    assert result['requests']==3
    assert 'metro_minutes' not in item
    assert osm.enrich_records([item])['cache_hits']==1
    assert len(calls)==3


def test_budget_durable_rate_and_daily(monkeypatch):
    now=[1000000.0]
    monkeypatch.setattr(osm.time,'time',lambda:now[0])
    assert osm._reserve('route') is None
    assert osm._reserve('route')=='rate_limit'
    for _ in range(59):
        now[0]+=2
        assert osm._reserve('route') is None
    now[0]+=2
    assert osm._reserve('route')=='daily_limit'
    now[0]+=86400
    assert osm._reserve('route') is None


def test_missing_coordinates_never_estimate():
    result=osm.enrich_records([{'address':'A'},dict(latitude=float('nan'),longitude=-46.6)])
    assert all(r['metro_status']=='coordinates_missing' and 'metro_minutes' not in r for r in result['records'])
    assert result['requests']==0


def test_catalog_filters_construction_and_duplicates(monkeypatch):
    monkeypatch.setattr(osm,'_reserve',lambda kind:None)
    def station(name, **tags):
        return dict(lat=-23.5,lon=-46.6,tags=dict(name=name,railway='station',station='subway',**tags))
    monkeypatch.setattr(osm,'_get',lambda *a,**k:{'elements':[station('A'),station('A'),station('B',construction='yes'),station('C',disused='yes')]})
    stations,reason=osm._stations(None)
    assert reason is None
    assert [s['name'] for s in stations]==['A']


def test_failed_provider_cooldown_and_no_fake_time(monkeypatch):
    osm._write('stations', {'at':osm.time.time(),'items':[dict(name='A',latitude=-23.5,longitude=-46.6)]})
    monkeypatch.setattr(osm,'_get',lambda *a,**k: (_ for _ in ()).throw(ValueError('invalid')))
    r=osm.enrich_records([dict(latitude=-23.55,longitude=-46.63)])['records'][0]
    assert r['metro_status']=='provider_unavailable'
    assert 'metro_minutes' not in r
    assert osm._reserve('route')=='provider_unavailable'

def test_partial_candidates_resume_without_claiming_best(monkeypatch):
    osm._write('stations', {'at':osm.time.time(),'items':[dict(name=str(i),latitude=-23.5,longitude=-46.6-i/100) for i in range(3)]})
    reservations=iter([None,'daily_limit'])
    monkeypatch.setattr(osm,'_reserve',lambda kind:next(reservations))
    monkeypatch.setattr(osm,'_get',lambda *a,**k:{'code':'Ok','routes':[dict(duration=180,distance=200)]})
    item=dict(latitude=-23.5,longitude=-46.6)
    first=osm.enrich_records([item])
    assert first['records'][0]['metro_status']=='daily_limit'
    assert 'metro_minutes' not in first['records'][0]
    monkeypatch.setattr(osm,'_reserve',lambda kind:None)
    second=osm.enrich_records([item])
    assert second['requests']==2
    assert second['records'][0]['metro_minutes']==3

def test_catalog_rate_limit_does_not_switch_hosts(monkeypatch):
    monkeypatch.setattr(osm,'_reserve',lambda kind:None)
    calls=[]
    def fail(client,url,**kw):
        calls.append(url)
        response=httpx.Response(429,request=httpx.Request('GET',url))
        response.raise_for_status()
    monkeypatch.setattr(osm,'_get',fail)
    with pytest.raises(httpx.HTTPStatusError):
        osm._stations(None)
    assert len(calls)==1


def test_catalog_overpass_output_keeps_node_coordinates():
    assert 'out body center' in osm.QUERY
    assert 'out center tags' not in osm.QUERY

def test_catalog_cooldown_does_not_suspend_routes(monkeypatch):
    osm._cooldown('catalog')
    assert osm._reserve('catalog')=='provider_unavailable'
    assert osm._reserve('route') is None


def test_partial_station_coverage_propagates(monkeypatch):
    osm._write('stations', {'at':osm.time.time(),'coverage':'partial','items':[dict(name='A',latitude=-23.5,longitude=-46.6)]})
    monkeypatch.setattr(osm,'_reserve',lambda kind:None)
    monkeypatch.setattr(osm,'_get',lambda *a,**k:{'code':'Ok','routes':[dict(duration=180,distance=200)]})
    result=osm.enrich_records([dict(latitude=-23.5,longitude=-46.6)])
    assert result['records'][0]['metro_station_coverage']=='partial'
