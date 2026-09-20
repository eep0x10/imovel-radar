from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, storage, saved_searches
from .domain import simulate_budget
from .ingestion import parse_upload
from .schemas import AccountUpdate, SavedSearchCreate, SavedSearchUpdate, AlertUpdate, Budget, CommitPreview, Login, Profile, PortalCreate, Register, SourceCreate, SourceUpdate, Tracking
from .security import hash_password, new_session, token_hash, verify_password
from .services import detail, enrich_all, ingest, profile_for, refresh_source

MAX_UPLOAD = 10 * 1024 * 1024
PORTALS = [("QuintoAndar", "https://www.quintoandar.com.br"), ("Loft", "https://loft.com.br"),
    ("ZAP Imóveis", "https://www.zapimoveis.com.br"), ("VivaReal", "https://www.vivareal.com.br"),
    ("OLX", "https://www.olx.com.br/imoveis"), ("Imovelweb", "https://www.imovelweb.com.br")]


@asynccontextmanager
async def lifespan(app):
    storage.initialize()
    yield


app = FastAPI(title="Imóvel Radar", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            msg = await receive()
            total += len(msg.get("body", b""))
            if total > MAX_UPLOAD + 512 * 1024:
                raise StarletteHTTPException(413, "Arquivo excede o limite de 10 MB")
            return msg
        await self.app(scope, limited_receive, send)


app.add_middleware(BodyLimit)


@app.middleware("http")
async def response_headers(request, call_next):
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > MAX_UPLOAD + 512 * 1024):
        return JSONResponse({"detail": "Requisição excede o limite de 10 MB"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    return response


def authenticated(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 200:
        raise HTTPException(401, "Entre na sua conta para continuar")
    hashed = token_hash(authorization[7:])
    with closing(storage.connect()) as conn:
        row = conn.execute("SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (hashed, storage.now_iso())).fetchone()
    if not row:
        raise HTTPException(401, "Sessão expirada. Entre novamente.")
    return dict(row)


User = Annotated[dict, Depends(authenticated)]


def limit_login(request, email):
    # DB-backed limit also applies across workers. Never store raw login input.
    client = request.client.host if request.client else "unknown"
    keys = [hashlib.sha256(("ip:" + client).encode()).hexdigest(), hashlib.sha256(("email:" + email.lower()).encode()).hexdigest()]
    now = storage.now_iso()
    until = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    with storage.transaction() as conn:
        for key in keys:
            row = conn.execute("SELECT * FROM login_limits WHERE key=?", (key,)).fetchone()
            cap = 60 if key == keys[0] else 12
            if row and row["until_at"] > now and row["attempts"] >= cap:
                raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos.")
        for key in keys:
            conn.execute("INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=CASE WHEN until_at<? THEN 1 ELSE attempts+1 END,until_at=CASE WHEN until_at<? THEN excluded.until_at ELSE until_at END", (key, until, now, now))


@app.post("/api/auth/register", status_code=201)
def register(payload: Register, request: Request):
    limit_login(request, payload.email)
    hashed = hash_password(payload.password)
    try:
        with storage.transaction() as conn:
            uid = conn.execute("INSERT INTO users(email,name,password_hash,profile,created_at) VALUES(?,?,?,?,?)", (payload.email, payload.name, hashed, storage.dumps(storage.DEFAULT_PROFILE), storage.now_iso())).lastrowid
            token = new_session(conn, uid)
        return {"token": token, "user": {"id": uid, "email": payload.email, "name": payload.name}}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Não foi possível criar esta conta. Confira o e-mail ou entre na conta existente.") from None


@app.post("/api/auth/login")
def login(payload: Login, request: Request):
    limit_login(request, payload.email)
    with closing(storage.connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (payload.email.strip().lower(),)).fetchone()
    # Do equivalent password work when the email does not exist.
    hashed = row["password_hash"] if row else hash_password("not-an-account-password")
    valid = verify_password(payload.password, hashed)
    if not row or not valid:
        raise HTTPException(401, "E-mail ou senha inválidos")
    with storage.transaction() as conn:
        token = new_session(conn, row["id"])
    return {"token": token, "user": {k: row[k] for k in ("id", "email", "name")}}


@app.get("/api/auth/me")
def me(user: User):
    return user


@app.post("/api/auth/logout")
def logout(user: User, authorization: Annotated[str, Header()]):
    with storage.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=? AND user_id=?", (token_hash(authorization[7:]), user["id"]))
    return {"ok": True}


@app.get("/api/profile")
def get_profile(user: User):
    with closing(storage.connect()) as conn:
        return profile_for(conn, user["id"])


@app.put("/api/profile")
def put_profile(payload: Profile, user: User):
    result = payload.model_dump()
    with storage.transaction() as conn:
        conn.execute("UPDATE users SET profile=? WHERE id=?", (storage.dumps(result), user["id"]))
    return result


@app.get("/api/properties")
def properties(user: User, q: str = Query(default="", max_length=200), sort: str = "fit", saved: bool = False, drops: bool = False,
               construction: Literal["all", "off_plan", "under_construction", "ready", "unknown"] = "all",
               apply_profile: bool = False, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100)):
    with closing(storage.connect()) as conn:
        items = enrich_all(conn, user["id"])
    today = datetime.now(timezone.utc).date().isoformat()
    summary = {"total": len(items), "new": sum(bool(p.get("first_seen") and p["first_seen"].startswith(today)) for p in items),
        "price_drops": sum((p["price_change"] or 0) < 0 for p in items), "saved": sum(p["saved"] for p in items)}
    last_updated = max((p["imported_at"] for p in items), default=None)
    filtered = [p for p in items if (not saved or p["saved"]) and (not drops or (p["price_change"] or 0) < 0)
        and (construction == "all" or p["construction_status"] == construction)
        and (not apply_profile or p["evaluation"]["eligible"])
        and (not q or q.casefold() in " ".join(str(p.get(k) or "") for k in ("title", "address", "neighborhood", "city", "source")).casefold())]
    if sort == "price":
        filtered.sort(key=lambda p: p["price"])
    elif sort == "price_m2":
        filtered.sort(key=lambda p: p["price"] / p["area"])
    elif sort == "opportunity":
        filtered.sort(key=lambda p: p["evaluation"].get("opportunity_percent") if p["evaluation"].get("opportunity_percent") is not None else -1e9, reverse=True)
    else:
        filtered.sort(key=lambda p: p["evaluation"].get("fit_score") if p["evaluation"].get("fit_score") is not None else -1, reverse=True)
    offset = (page - 1) * page_size
    return {"items": filtered[offset:offset + page_size], "total": len(filtered), "page": page, "page_size": page_size, "summary": summary, "last_updated": last_updated}


@app.get("/api/properties/{pid}")
def property_detail(pid: int, user: User):
    with closing(storage.connect()) as conn:
        result = detail(conn, user["id"], pid)
    if not result:
        raise HTTPException(404, "Imóvel não encontrado")
    return result


@app.post("/api/properties", status_code=201)
def create_property(payload: dict, user: User):
    payload["source"] = payload.get("source") or "Manual"
    payload["external_id"] = payload.get("external_id") or secrets.token_hex(12)
    try:
        parsed = parse_upload(storage.dumps([payload]).encode(), "manual.json")
    except (ValueError, TypeError):
        raise HTTPException(422, "Dados do imóvel inválidos") from None
    if parsed["errors"] or not parsed["records"]:
        raise HTTPException(422, parsed["errors"] or "Nenhum imóvel válido")
    with storage.transaction() as conn:
        ingest(conn, user["id"], parsed["records"], "manual")
        r = parsed["records"][0]
        pid = conn.execute("SELECT id FROM properties WHERE user_id=? AND source=? AND external_id=?", (user["id"], r["source"], r["external_id"])).fetchone()[0]
        return detail(conn, user["id"], pid)


@app.patch("/api/properties/{pid}/tracking")
def tracking(pid: int, payload: Tracking, user: User):
    uid = user["id"]
    with storage.transaction() as conn:
        if not conn.execute("SELECT 1 FROM properties WHERE user_id=? AND id=?", (uid, pid)).fetchone():
            raise HTTPException(404, "Imóvel não encontrado")
        conn.execute("INSERT OR IGNORE INTO tracking(user_id,property_id,updated_at) VALUES(?,?,?)", (uid, pid, storage.now_iso()))
        for key, value in payload.model_dump(exclude_unset=True).items():
            if value is None and key != "visit_at":
                continue
            if key in {"checklist", "assessments"}:
                value = storage.dumps(value)
            # Keys come only from the closed Pydantic schema.
            conn.execute(f"UPDATE tracking SET {key}=?,updated_at=? WHERE user_id=? AND property_id=?", (value, storage.now_iso(), uid, pid))
        return detail(conn, uid, pid)


@app.post("/api/import/preview")
def import_preview(user: User, file: UploadFile = File(...)):
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo excede 10 MB")
    try:
        parsed = parse_upload(content, file.filename or "upload.csv")
    except ValueError:
        raise HTTPException(422, "Não foi possível ler este arquivo") from None
    return save_preview(user, parsed)


def save_preview(user, parsed):
    preview_id = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    with storage.transaction() as conn:
        # Bound retained pending upload size per account.
        conn.execute("DELETE FROM previews WHERE user_id=? AND expires_at<?", (user["id"], storage.now_iso()))
        count = conn.execute("SELECT COUNT(*) FROM previews WHERE user_id=? AND committed_result IS NULL", (user["id"],)).fetchone()[0]
        if count >= 10:
            raise HTTPException(429, "Há dez prévias pendentes. Confirme uma delas ou aguarde 30 minutos.")
        conn.execute("INSERT INTO previews VALUES(?,?,?,?,?,?,?,NULL)", (preview_id, user["id"], storage.dumps(parsed["records"]), storage.dumps(parsed["errors"]), storage.dumps(parsed["warnings"]), storage.now_iso(), expires))
    return {"preview_id": preview_id, "records": parsed["records"][:20], "errors": parsed["errors"], "warnings": parsed["warnings"], "total": len(parsed["records"]) + len(parsed["errors"]), "valid": len(parsed["records"])}


@app.post("/api/import/legacy-preview")
def legacy_preview(user: User):
    # Only the owner of the local installation can expose this migration convenience.
    if os.environ.get("IMOVEL_ENABLE_LEGACY_IMPORT") != "1" or user["id"] != 1:
        raise HTTPException(404, "Importação local não habilitada")
    path = storage.ROOT / "resultados_quintoandar.xlsx"
    if not path.is_file():
        raise HTTPException(404, "Planilha legada não encontrada")
    return save_preview(user, parse_upload(path.read_bytes(), path.name))


@app.post("/api/import/commit")
def commit_preview(payload: CommitPreview, user: User):
    with storage.transaction() as conn:
        preview = conn.execute("SELECT * FROM previews WHERE id=? AND user_id=?", (payload.preview_id, user["id"])).fetchone()
        if not preview:
            raise HTTPException(404, "Prévia não encontrada")
        if preview["committed_result"]:
            return json.loads(preview["committed_result"])
        if preview["expires_at"] < storage.now_iso():
            raise HTTPException(410, "Prévia expirada. Envie o arquivo novamente.")
        if json.loads(preview["errors"]):
            raise HTTPException(422, "Corrija os erros do arquivo antes de importar")
        result = ingest(conn, user["id"], json.loads(preview["records"]))
        conn.execute("UPDATE previews SET committed_result=? WHERE id=?", (storage.dumps(result), payload.preview_id))
        return result


@app.get("/api/import/template.csv")
def import_template(user: User):
    fields = ["source", "external_id", "url", "title", "price", "area", "address", "neighborhood", "city", "property_type", "bedrooms", "bathrooms", "parking", "condo_fee", "property_tax", "tax_period", "metro_minutes", "observed_at", "status"]
    out = io.StringIO()
    csv.writer(out).writerow(fields)
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="modelo-imoveis.csv"'})


def schedule_info(conn):
    row = conn.execute("SELECT value FROM runtime WHERE key='worker_heartbeat'").fetchone()
    heartbeat = row[0] if row else None
    stale = not heartbeat or heartbeat < (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    return {"hour": int(os.environ.get("IMOVEL_REFRESH_HOUR", "7")), "timezone": os.environ.get("IMOVEL_TIMEZONE", "America/Sao_Paulo"), "worker_heartbeat": heartbeat, "worker_status": "offline" if stale else "running"}


@app.get("/api/sources")
def sources(user: User):
    with closing(storage.connect()) as conn:
        items = [dict(r) for r in conn.execute("SELECT s.*, (SELECT COUNT(*) FROM properties p WHERE p.source_id=s.id AND p.user_id=s.user_id) AS record_count FROM sources s WHERE s.user_id=? ORDER BY s.id", (user["id"],))]
        schedule = schedule_info(conn)
        for item in items:
            run = conn.execute("SELECT summary FROM runs WHERE source_id=? AND user_id=? AND status='success' ORDER BY id DESC LIMIT 1", (item["id"], user["id"])).fetchone()
            item["last_result"] = json.loads(run[0]) if run else None
    for item in items:
        item.pop("user_id", None)
        item["enabled"] = bool(item["enabled"])
        item["authorized"] = bool(item["authorized"])
    enabled_portals = {"QuintoAndar": "quintoandar", "Loft": "loft", "VivaReal": "vivareal", "OLX": "olx"}
    catalog = [{"name": name, "url": url, "portal": enabled_portals.get(name),
                "supported": name in enabled_portals,
                "status": "available" if name in enabled_portals else "access_blocked",
                "message": None if name in enabled_portals else "O portal bloqueou a coleta HTTP na última verificação. Importação de arquivo continua disponível."} for name, url in PORTALS]
    return {"items": items, "catalog": catalog, "schedule": schedule}


@app.post("/api/sources/portal", status_code=201)
def add_portal(payload: PortalCreate, user: User):
    name, url = {"quintoandar": PORTALS[0], "loft": PORTALS[1], "vivareal": PORTALS[3], "olx": PORTALS[4]}[payload.portal]
    with storage.transaction() as conn:
        conn.execute("INSERT INTO sources(user_id,name,kind,url,enabled,authorized,status,created_at) VALUES(?,?,'portal',?,1,1,'pending',?) ON CONFLICT(user_id,name,kind) DO UPDATE SET enabled=1,authorized=1", (user["id"], name, url, storage.now_iso()))
        sid = conn.execute("SELECT id FROM sources WHERE user_id=? AND name=? AND kind='portal'", (user["id"], name)).fetchone()[0]
    return {"id": sid, "portal": payload.portal}



@app.post("/api/sources", status_code=201)
def add_source(payload: SourceCreate, user: User):
    parsed = urlsplit(payload.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "Use a URL pública HTTP/HTTPS do feed, sem usuário/senha ou fragmento")
    # Full DNS/IP verification occurs on every fetch (including worker runs).
    try:
        with storage.transaction() as conn:
            sid = conn.execute("INSERT INTO sources(user_id,name,kind,url,enabled,authorized,status,created_at) VALUES(?,?,'feed',?,1,1,'pending',?)", (user["id"], payload.name.strip(), payload.url, storage.now_iso())).lastrowid
        return {"id": sid, "name": payload.name, "status": "pending", "enabled": True, "authorized": True}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Já existe uma fonte com esse nome") from None


@app.patch("/api/sources/{sid}")
def update_source(sid: int, payload: SourceUpdate, user: User):
    try:
        with storage.transaction() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=? AND user_id=? AND kind IN ('feed','portal')", (sid, user["id"])).fetchone()
            if not row:
                raise HTTPException(404, "Fonte não encontrada")
            if payload.enabled is not None:
                conn.execute("UPDATE sources SET enabled=? WHERE id=?", (payload.enabled, sid))
            if payload.name is not None:
                # The source name is also the immutable namespace for listing identity.
                raise HTTPException(422, "O nome identifica os anúncios desta fonte e não pode ser alterado. Você pode pausar a fonte.")
        return {"ok": True}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Nome de fonte já utilizado") from None


@app.post("/api/sources/{sid}/refresh")
def refresh_one(sid: int, user: User):
    with closing(storage.connect()) as conn:
        if not conn.execute("SELECT 1 FROM sources WHERE id=? AND user_id=?", (sid, user["id"])).fetchone():
            raise HTTPException(404, "Fonte não encontrada")
    try:
        return refresh_source(user["id"], sid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/refresh")
def refresh_all(user: User):
    with closing(storage.connect()) as conn:
        rows = conn.execute("SELECT id,name FROM sources WHERE user_id=? AND kind IN ('feed','portal') AND enabled=1 AND authorized=1", (user["id"],)).fetchall()
    results = []
    for row in rows:
        try:
            results.append({"source_id": row["id"], "name": row["name"], "status": "success", "result": refresh_source(user["id"], row["id"])})
        except ValueError as exc:
            results.append({"source_id": row["id"], "name": row["name"], "status": "error", "error": str(exc)})
    return {"results": results, "message": "Atualizações concluídas" if results else "Nenhuma fonte de coleta está habilitada. Configure uma fonte para atualização diária."}


@app.patch("/api/account")
def update_account(payload: AccountUpdate, user: User):
    with storage.transaction() as conn:
        conn.execute("UPDATE users SET name=? WHERE id=?", (payload.name, user["id"]))
    return {**user, "name": payload.name}


@app.get("/api/saved-searches")
def get_saved_searches(user: User):
    with closing(storage.connect()) as conn:
        return {"items": saved_searches.searches(conn, user["id"])}


@app.post("/api/saved-searches", status_code=201)
def create_saved_search(payload: SavedSearchCreate, user: User):
    with storage.transaction() as conn:
        if conn.execute("SELECT COUNT(*) FROM saved_searches WHERE user_id=?", (user["id"],)).fetchone()[0] >= 50:
            raise HTTPException(422, "Limite de 50 buscas salvas por conta")
        return saved_searches.create(conn, user["id"], payload.model_dump())


@app.patch("/api/saved-searches/{sid}")
def update_saved_search(sid: int, payload: SavedSearchUpdate, user: User):
    with storage.transaction() as conn:
        if conn.execute("UPDATE saved_searches SET enabled=?,updated_at=? WHERE id=? AND user_id=?",
                        (payload.enabled, storage.now_iso(), sid, user["id"])).rowcount != 1:
            raise HTTPException(404, "Busca não encontrada")
        created = saved_searches.reconcile(conn, user["id"], sid) if payload.enabled else 0
        return {**next(s for s in saved_searches.searches(conn, user["id"]) if s['id'] == sid), "notifications_created": created}


@app.get("/api/notifications")
def get_notifications(user: User, page: int = Query(default=1, ge=1),
                      page_size: int = Query(default=50, ge=1, le=100), unread_only: bool = False):
    with closing(storage.connect()) as conn:
        return saved_searches.notifications(conn, user["id"], page, page_size, unread_only)


@app.patch("/api/notifications/read-all")
def read_all_notifications(user: User):
    with storage.transaction() as conn:
        updated = conn.execute("UPDATE alerts SET read=1 WHERE user_id=? AND saved_search_id IS NOT NULL AND read=0", (user["id"],)).rowcount
    return {"ok": True, "updated": updated}


@app.get("/api/alerts")
def alerts(user: User):
    with closing(storage.connect()) as conn:
        items = [dict(r) for r in conn.execute("SELECT id,property_id,kind,title,body,created_at,read FROM alerts WHERE user_id=? ORDER BY id DESC LIMIT 200", (user["id"],))]
        unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE user_id=? AND read=0", (user["id"],)).fetchone()[0]
    return {"items": items, "unread": unread}


@app.patch("/api/alerts/{aid}")
def read_alert(aid: int, payload: AlertUpdate, user: User):
    with storage.transaction() as conn:
        if conn.execute("UPDATE alerts SET read=? WHERE id=? AND user_id=?", (payload.read, aid, user["id"])).rowcount != 1:
            raise HTTPException(404, "Alerta não encontrado")
    return {"ok": True}


@app.post("/api/budget")
def budget(payload: Budget, user: User):
    try:
        return simulate_budget(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/export")
def export_account(user: User):
    with closing(storage.connect()) as conn:
        items = enrich_all(conn, user["id"])
        for item in items:
            item["history"] = [dict(r) for r in conn.execute("SELECT price,observed_at,recorded_at FROM observations WHERE property_id=? ORDER BY id", (item["id"],))]
        result = {"version": __version__, "exported_at": storage.now_iso(), "user": user, "profile": profile_for(conn, user["id"]), "properties": items,
            "historical_alerts": [dict(r) for r in conn.execute("SELECT id,property_id,kind,title,body,created_at,read FROM alerts WHERE user_id=? AND saved_search_id IS NULL ORDER BY id", (user["id"],))],
            "saved_searches": saved_searches.searches(conn, user["id"]),
            "notifications": [dict(r) for r in conn.execute("SELECT id,property_id,kind,title,body,created_at,read,saved_search_id FROM alerts WHERE user_id=? AND saved_search_id IS NOT NULL ORDER BY id", (user["id"],))],
            "sources": [dict(r) for r in conn.execute("SELECT name,kind,url,status,enabled,last_success FROM sources WHERE user_id=?", (user["id"],))]}
    return JSONResponse(result, headers={"Content-Disposition": 'attachment; filename="meus-imoveis.json"'})


@app.get("/api/health")
def health():
    with closing(storage.connect()) as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "version": __version__}


@app.get("/api/status")
def status(user: User):
    from .location_enrichment import provider_status
    with closing(storage.connect()) as conn:
        return {"integrations": {"google_maps": provider_status()}, "schedule": schedule_info(conn), "legacy_import_available": os.environ.get("IMOVEL_ENABLE_LEGACY_IMPORT") == "1" and user["id"] == 1 and (storage.ROOT / "resultados_quintoandar.xlsx").is_file()}


@app.get("/api/{unknown:path}")
def unknown_api(unknown: str):
    raise HTTPException(404, "Endpoint não encontrado")


WEB = storage.ROOT / "web"
WEB.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
