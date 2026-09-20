"""Repair adapter metadata, preserving prices, history and generic imports."""
import json
import math

KEY = "migration:quinto-monthly-cost:v1"


def repair_portal_cost_periods(conn):
    if conn.execute("SELECT 1 FROM runtime WHERE key=?", (KEY,)).fetchone():
        return 0
    rows = conn.execute("""SELECT p.id,p.data FROM properties p JOIN sources s
        ON p.source_id=s.id AND p.user_id=s.user_id
        WHERE p.source='QuintoAndar' AND s.name='QuintoAndar' AND s.kind='portal'""").fetchall()
    repaired = 0
    for row in rows:
        data = json.loads(row[1])
        value = data.get("combined_monthly_cost")
        if data.get("combined_cost_period") != "unknown" or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            continue
        data["combined_cost_period"] = "monthly"
        data.setdefault("provenance", {})["combined_cost_period"] = {
            "source": "QuintoAndar sale search / iptuPlusCondominium",
            "observed_at": data.get("observed_at"),
            "normalization": "monthly-cost-v1",
        }
        conn.execute("UPDATE properties SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), row[0]))
        repaired += 1
    conn.execute("INSERT INTO runtime(key,value) VALUES(?,?)", (KEY, json.dumps({"repaired": repaired})))
    return repaired
