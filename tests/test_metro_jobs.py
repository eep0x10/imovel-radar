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


def test_background_routes_persist_without_price_history_or_recollection(tmp_path,monkeypatch):
    monkeypatch.setenv("IMOVEL_DB_PATH",str(tmp_path/'metro.sqlite3'))
    monkeypatch.delenv("IMOVEL_METRO_PROVIDER",raising=False)
    storage.initialize()
    with storage.transaction() as c:
        c.execute("INSERT INTO users(id,email,name,password_hash,profile,created_at) VALUES(1,'qa@example.test','QA','test','{}','2026-09-20')")
        data={"source":"QA","external_id":"x","price":300000,"latitude":-23.5,"longitude":-46.6}
        c.execute("INSERT INTO properties(id,user_id,source,external_id,data,imported_at,canonical_key) VALUES(1,1,'QA','x',?,'2026-09-20','qa')",(json.dumps(data),))
    monkeypatch.setattr(metro_jobs,'google_enrich',lambda records,profile:{'records':records})
    from app import osm_walking
    def routed(records,profile):
        return {'records':[{**r,'metro_minutes':12,'metro_station':'Belém','metro_route_source':'OSM','metro_checked_at':datetime.now(timezone.utc).isoformat()} for r in records]}
    monkeypatch.setattr(osm_walking,'enrich_records',routed)
    assert metro_jobs.cycle()['enriched']==1
    assert metro_jobs.cycle()['status']=='waiting'
    with storage.connect() as c:
        p=json.loads(c.execute('select data from properties').fetchone()[0])
        assert p['price']==300000 and p['metro_minutes']==12 and p['metro_status']=='ready'
        assert c.execute('select count(*) from observations').fetchone()[0]==0
