"""Ingestion transactions, evaluations, history and failure-safe refresh."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta, timezone

from . import storage
from .domain import evaluate_property, evaluate_many
from .sale_scope import rental_listing


def digest(value):
    return hashlib.sha256(storage.dumps(value).encode()).hexdigest()


def observation_content(record):
    """Compare facts and attribution, excluding only observation timestamps."""
    value = {k: v for k, v in record.items() if k != "observed_at"}
    if isinstance(value.get("provenance"), dict):
        value["provenance"] = {field: {k: v for k, v in metadata.items() if k != "observed_at"}
                               if isinstance(metadata, dict) else metadata
                               for field, metadata in value["provenance"].items()}
    return value


def latest_price_change(price, prices):
    """Last distinct price event survives refreshed sightings and metadata edits."""
    previous = next((value for value in reversed(prices) if value != price), None)
    return price - previous if previous is not None else None


def recent_price_change(history, now=None):
    """Latest actual price transition observed within 30 days, not metadata refreshes."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    previous = None
    latest = None
    for row in history:
        price = row.get("price")
        if price is None:
            continue
        if previous is not None and price != previous:
            # Unknown observation dates cannot establish when a price changed.
            try:
                at = datetime.fromisoformat(row.get("observed_at") or "")
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                at = None
            latest = ({"previous_price": previous, "price": price,
                       "amount": price - previous,
                       "percent": round((price - previous) / previous * 100, 1) if previous else None,
                       "observed_at": at.isoformat()}
                      if at and cutoff <= at <= now else None)
        previous = price
    return latest


def profile_for(conn, user_id):
    return {**storage.DEFAULT_PROFILE, **json.loads(conn.execute("SELECT profile FROM users WHERE id=?", (user_id,)).fetchone()[0])}


def canonical_key(record):
    # Building addresses alone never establish that two listings are the same unit.
    address = str(record.get("address") or "")
    unit = re.search(r"\b(?:apto|apartamento|ap\.|unidade)\s*([a-z0-9-]+)\b", address, re.I)
    if unit and record.get("city") and re.search(r"\d", address):
        text = f"{record['city']}|{address}|{record.get('area')}"
        normalized = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
        return "unit:" + digest(re.sub(r"\s+", " ", normalized))
    return "listing:" + digest([record["source"], record["external_id"]])


def alert(conn, user_id, property_id, kind, title, body, key):
    cursor = conn.execute("INSERT OR IGNORE INTO alerts(user_id,property_id,kind,title,body,created_at,dedupe_key) VALUES(?,?,?,?,?,?,?)",
        (user_id, property_id, kind, title, body, storage.now_iso(), key))
    return cursor.rowcount


def ingest(conn, user_id, records, origin="import", source_id=None):
    result = {"created": 0, "updated": 0, "unchanged": 0, "alerts": 0, "errors": []}
    profile = profile_for(conn, user_id)
    timestamp = storage.now_iso()
    for original in records:
        record = dict(original)
        if rental_listing(record):
            result["errors"].append("Anúncio de aluguel ignorado: sistema exclusivo para compra.")
            continue
        record.pop("id", None)
        record["data_origin"] = origin
        record["source"] = str(record.get("source") or "Manual").strip()
        record["external_id"] = str(record.get("external_id") or digest(record))
        source = record["source"]
        sid = source_id
        if sid is None:
            conn.execute("INSERT OR IGNORE INTO sources(user_id,name,kind,status,created_at) VALUES(?,?,'import','imported',?)", (user_id, source, timestamp))
            sid = conn.execute("SELECT id FROM sources WHERE user_id=? AND name=? AND kind='import'", (user_id, source)).fetchone()[0]
        existing = conn.execute("SELECT * FROM properties WHERE user_id=? AND source=? AND external_id=?", (user_id, source, record["external_id"])).fetchone()
        observed = record.get("observed_at")
        previous = json.loads(existing["data"]) if existing else None
        from .metro_jobs import preserve_route
        preserve_route(record, previous)
        # Undated legacy imports cannot replace a fresher timestamped observation.
        old_date = previous.get("observed_at") if previous else None
        def instant(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        if old_date and (not observed or instant(observed) < instant(old_date)):
            result["unchanged"] += 1
            continue
        if previous == record:
            result["unchanged"] += 1
            continue
        if previous and observation_content(previous) == observation_content(record):
            # A fresh sighting is useful, but it is not a price/data change and
            # must not duplicate the history or emit another alert.
            conn.execute("UPDATE properties SET data=?,last_seen=?,imported_at=? WHERE id=? AND user_id=?",
                (storage.dumps(record), observed or existing["last_seen"], timestamp, existing["id"], user_id))
            result["unchanged"] += 1
            continue
        key = canonical_key(record)
        if existing:
            pid = existing["id"]
            conn.execute("UPDATE properties SET source_id=?,data=?,last_seen=?,imported_at=?,canonical_key=? WHERE id=? AND user_id=?",
                (sid, storage.dumps(record), observed or existing["last_seen"], timestamp, key, pid, user_id))
            result["updated"] += 1
        else:
            cursor = conn.execute("INSERT INTO properties(user_id,source_id,source,external_id,data,first_seen,last_seen,imported_at,canonical_key) VALUES(?,?,?,?,?,?,?,?,?)",
                (user_id, sid, source, record["external_id"], storage.dumps(record), observed, observed, timestamp, key))
            pid = cursor.lastrowid
            result["created"] += 1
        # Consecutive identical observations were skipped above; returning to an
        # earlier price is a new event, not a globally duplicate observation.
        predecessor = conn.execute("SELECT MAX(id) FROM observations WHERE property_id=?", (pid,)).fetchone()[0]
        fingerprint = digest([record["price"], observed, digest(record), predecessor])
        conn.execute("INSERT OR IGNORE INTO observations(property_id,price,observed_at,recorded_at,fingerprint) VALUES(?,?,?,?,?)",
            (pid, record["price"], observed, timestamp, fingerprint))
        if not previous:
            evaluation = evaluate_property({**record, "id": pid, "canonical_key": key}, [], profile)
            if evaluation["eligible"]:
                result["alerts"] += alert(conn, user_id, pid, "new", "Novo imóvel na sua busca", record.get("title") or f"{source} · {record['external_id']}", f"new:{pid}")
        elif previous.get("price", 0) > record["price"]:
            percent = (previous["price"] - record["price"]) / previous["price"] * 100
            if percent >= profile.get("alert_drop_percent", 5):
                result["alerts"] += alert(conn, user_id, pid, "price_drop", f"Preço caiu {percent:.1f}%",
                    f"De R$ {previous['price']:,.2f} para R$ {record['price']:,.2f}. Confirme a disponibilidade na fonte.", f"drop:{pid}:{fingerprint}")
        if source_id is None:
            conn.execute("UPDATE sources SET last_attempt=?,last_success=?,status='imported',error=NULL WHERE id=? AND user_id=?", (timestamp, timestamp, sid, user_id))
    from .saved_searches import reconcile
    result["notifications"] = reconcile(conn, user_id)
    return result


def all_properties(conn, user_id):
    rows = conn.execute("SELECT * FROM properties WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    return [item for row in rows if not rental_listing(item := storage.load_property(row))]


def enrich_all(conn, user_id):
    items = all_properties(conn, user_id)
    profile = profile_for(conn, user_id)
    track = {r["property_id"]: dict(r) for r in conn.execute("SELECT * FROM tracking WHERE user_id=?", (user_id,))}
    # Batch price reads rather than N extra queries.
    histories = {}
    for row in conn.execute("SELECT o.* FROM observations o JOIN properties p ON p.id=o.property_id WHERE p.user_id=? ORDER BY o.id", (user_id,)):
        histories.setdefault(row["property_id"], []).append(dict(row))
    for item in items:
        t = track.get(item["id"], {})
        item.update(saved=bool(t.get("saved")), stage=t.get("stage", "saved"), notes=t.get("notes", ""),
            visit_at=t.get("visit_at"), checklist=json.loads(t.get("checklist", "{}")), assessments=json.loads(t.get("assessments", "{}")))
        # A user's visit assessment survives future feed updates; it is never
        # silently written back into the source's raw listing.
        for key, value in item["assessments"].items():
            if value != "unknown":
                item[key] = value
        prices = histories.get(item["id"], [])
        item["price_change"] = latest_price_change(item["price"], [row["price"] for row in prices])
        item["price_change_30d"] = recent_price_change(prices)
    for item, evaluation in zip(items, evaluate_many(items, profile)):
        item["evaluation"] = evaluation
    return items


def detail(conn, user_id, pid):
    values = all_properties(conn, user_id)
    item = next((p for p in values if p["id"] == pid), None)
    if not item:
        return None
    tracking_row = conn.execute("SELECT * FROM tracking WHERE user_id=? AND property_id=?", (user_id, pid)).fetchone()
    t = dict(tracking_row) if tracking_row else {}
    item.update(saved=bool(t.get("saved")), stage=t.get("stage", "saved"), notes=t.get("notes", ""), visit_at=t.get("visit_at"),
        checklist=json.loads(t.get("checklist", "{}")), assessments=json.loads(t.get("assessments", "{}")))
    for key, value in item["assessments"].items():
        if value != "unknown":
            item[key] = value
    item["evaluation"] = evaluate_property(item, values, profile_for(conn, user_id))
    item["history"] = [dict(r) for r in conn.execute("SELECT price,observed_at,recorded_at FROM observations WHERE property_id=? ORDER BY id", (pid,))]
    item["price_change"] = latest_price_change(item["price"], [row["price"] for row in item["history"]])
    item["price_change_30d"] = recent_price_change(item["history"])
    item["source_links"] = [{"source": p["source"], "url": p.get("url")} for p in values if p["canonical_key"] == item["canonical_key"]]
    item["provenance"] = {k: {"source": item["source"], "observed_at": item.get("observed_at"), "origin": item["data_origin"]}
        for k in ("price", "area", "address", "condo_fee", "property_tax", "metro_minutes") if item.get(k) is not None}
    for key, value in item.get("assessments", {}).items():
        if value != "unknown":
            item["provenance"][key] = {"source": "Sua avaliação", "origin": "user_assessment", "observed_at": None}
    item["alerts"] = [dict(r) for r in conn.execute("SELECT id,kind,title,body,created_at,read FROM alerts WHERE user_id=? AND property_id=? ORDER BY id DESC LIMIT 100", (user_id, pid))]
    return item


def acquire_lock(name, minutes=10):
    owner = secrets.token_hex(16)
    now = storage.now_iso()
    until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    with storage.transaction() as conn:
        current = conn.execute("SELECT expires_at FROM locks WHERE name=?", (name,)).fetchone()
        if current and current[0] > now:
            return None
        conn.execute("INSERT INTO locks VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET expires_at=excluded.expires_at,owner=excluded.owner", (name, until, owner))
    return owner


def release_lock(name, owner):
    with storage.transaction() as conn:
        conn.execute("DELETE FROM locks WHERE name=? AND owner=?", (name, owner))


def renew_lock(name, owner, minutes=15):
    until = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    with storage.transaction() as conn:
        return conn.execute("UPDATE locks SET expires_at=? WHERE name=? AND owner=?", (until, name, owner)).rowcount == 1


def refresh_source(user_id, source_id, search_profile=None):
    from .ingestion import fetch_feed
    name = f"source:{source_id}"
    owner = acquire_lock(name)
    if not owner:
        raise ValueError("Esta fonte já está sendo atualizada. Tente novamente depois.")
    run_id = None
    try:
        with storage.transaction() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=? AND user_id=?", (source_id, user_id)).fetchone()
            if not row or row["kind"] not in {"feed", "portal"} or not row["enabled"] or not row["authorized"]:
                raise ValueError("Fonte não habilitada ou não autorizada")
            source = dict(row)
            conn.execute("UPDATE sources SET last_attempt=?,status='running',error=NULL WHERE id=?", (storage.now_iso(), source_id))
            run_id = conn.execute("INSERT INTO runs(user_id,source_id,started_at,status) VALUES(?,?,?,'running')", (user_id, source_id, storage.now_iso())).lastrowid
        if source["kind"] == "portal":
            from .portal_collectors import collect_portal
            with closing(storage.connect()) as conn:
                search_profile = search_profile if search_profile is not None else profile_for(conn, user_id)
            portal = {"QuintoAndar": "quintoandar", "Loft": "loft"}.get(source["name"])
            if not portal:
                raise ValueError("Coletor não disponível para esta fonte")
            parsed = collect_portal(portal, search_profile)
        else:
            parsed = fetch_feed(source["url"])
        if parsed.get("errors"):
            raise ValueError("Coleta incompleta ou dados inválidos; dados anteriores preservados. " + (str(parsed["errors"][0].get("message", "Confira a fonte."))[:250] if source["kind"] == "portal" else "Corrija o arquivo e tente novamente."))
        if not parsed.get("records") and source["kind"] != "portal":
            raise ValueError("Feed vazio; dados anteriores preservados. Ausência não confirma indisponibilidade.")
        # Preserve original portal identity within a stable feed namespace.
        # Aggregated feeds can legitimately contain Loft/1 and QuintoAndar/1.
        # Fetch time is an actual observation of the feed, distinct from an
        # undated uploaded historical file. Keep provided source dates intact.
        fetched_at = storage.now_iso()
        records = [{**r, "external_id": f"feed:{source_id}:{r['external_id']}" if source["kind"] == "feed" else r["external_id"], "feed_name": source["name"],
            "observed_at": r.get("observed_at") or fetched_at} for r in parsed["records"]]
        if source["kind"] == "portal":
            from .portal_collectors import enrich_quinto_details
            details = enrich_quinto_details(records)
            records = details["records"]
            parsed.setdefault("warnings", []).extend(details["warnings"])
            from .location_enrichment import enrich_records
            enriched = enrich_records(records, search_profile)
            records = enriched["records"]
            parsed.setdefault("warnings", []).extend(enriched["warnings"])
            parsed["enrichment"] = {key: value for key, value in enriched.items() if key not in {"records", "warnings"}}
        with storage.transaction() as conn:
            result = ingest(conn, user_id, records, source["kind"], source_id)
            result["coverage"] = parsed.get("coverage")
            result["warnings"] = parsed.get("warnings", [])
            result["enrichment"] = parsed.get("enrichment")
            state = "partial" if parsed.get("coverage") and not parsed["coverage"]["complete"] else "healthy"
            conn.execute("UPDATE sources SET status=?,last_success=?,error=NULL WHERE id=?", (state, storage.now_iso(), source_id))
            conn.execute("UPDATE runs SET finished_at=?,status='success',summary=? WHERE id=?", (storage.now_iso(), storage.dumps(result), run_id))
        return result
    except Exception as exc:
        # No URLs, response bodies or credentials in public error/logs.
        message = str(exc) if isinstance(exc, ValueError) else "Falha ao consultar o feed. Verifique acesso, formato e disponibilidade."
        message = message[:500]
        if run_id:
            with storage.transaction() as conn:
                conn.execute("UPDATE sources SET status='error',error=? WHERE id=? AND user_id=?", (message, source_id, user_id))
                conn.execute("UPDATE runs SET finished_at=?,status='failed',error=? WHERE id=?", (storage.now_iso(), message, run_id))
        raise ValueError(message) from None
    finally:
        release_lock(name, owner)
