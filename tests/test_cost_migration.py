import json
from app import storage
from app.cost_migration import KEY, repair_portal_cost_periods


def test_cost_repair_is_scoped_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("IMOVEL_DB_PATH", str(tmp_path / "costs.sqlite3"))
    storage.initialize()
    with storage.transaction() as c:
        c.execute("DELETE FROM runtime WHERE key=?", (KEY,))
        c.execute("INSERT INTO users(id,email,name,password_hash,profile,created_at) VALUES(1,'qa@example.test','QA','test','{}','2026-09-20')")
        c.execute("INSERT INTO sources(id,user_id,name,kind,created_at) VALUES(1,1,'QuintoAndar','portal','2026-09-20')")
        for pid, sid in ((1, 1), (2, None)):
            data = json.dumps({"price": 300000, "combined_monthly_cost": 700, "combined_cost_period": "unknown"})
            c.execute("INSERT INTO properties(id,user_id,source_id,source,external_id,data,imported_at,canonical_key) VALUES(?,1,?,'QuintoAndar',?,?,'2026-09-20',?)", (pid,sid,str(pid),data,str(pid)))
        assert repair_portal_cost_periods(c) == 1
        rows = [json.loads(r[0]) for r in c.execute("SELECT data FROM properties ORDER BY id")]
        assert rows[0]["combined_cost_period"] == "monthly"
        assert rows[1]["combined_cost_period"] == "unknown"
        assert all(p["price"] == 300000 for p in rows)
        assert repair_portal_cost_periods(c) == 0
        assert c.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
