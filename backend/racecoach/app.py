from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

from .db import Database, dump, uid
from .models import Login, PlanCreate, PlanItemCreate, PlanItemUpdate, StationCreate, TraineeCreate
from .security import LoginLimiter, digest, new_token, password_hash, password_matches

COOKIE = "racecoach_session"
ROOT = Path(__file__).resolve().parents[2]


def require_row(db, table, row_id):
    # table names are application constants, never client input.
    row = db.one(f"SELECT * FROM {table} WHERE id=?", (row_id,))
    if not row:
        raise HTTPException(404, "Nie znaleziono rekordu")
    return row


def user(request: Request):
    token = request.cookies.get(COOKIE, "")
    row = request.app.state.db.one(
        "SELECT u.id,u.email,u.name,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.expires>?", (digest(token), time.time()))
    if not row:
        raise HTTPException(401, "Zaloguj się, aby kontynuować")
    return row


def instructor(current=Depends(user)):
    if current["role"] not in ("instructor", "service"):
        raise HTTPException(403, "Ta operacja wymaga uprawnień instruktora")
    return current


def station(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Brak tokenu stanowiska")
    row = request.app.state.db.one("SELECT * FROM stations WHERE token_hash=?", (digest(auth[7:]),))
    if not row:
        raise HTTPException(401, "Niepoprawny token stanowiska")
    return row


def create_app(data_dir: str | Path | None = None, demo=False, bootstrap_admin=True):
    data_dir = Path(data_dir or os.environ.get("RACECOACH_DATA", ROOT / ".local"))
    db = Database(data_dir / "racecoach.sqlite3")
    limiter = LoginLimiter()

    @asynccontextmanager
    async def lifespan(app):
        if bootstrap_admin and not db.one("SELECT id FROM users LIMIT 1"):
            token = "Trening2026!" if demo else new_token()[:20]
            email = "instruktor@demo.local" if demo else "instruktor@local"
            with db.transaction() as c:
                c.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                          (uid(), email, "Michał · instruktor", "instructor", password_hash(token), time.time()))
            credentials = data_dir / "bootstrap.json"
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(dump({"email": email, "password": token, "demo": demo}))
        task = None
        if demo:
            import asyncio
            from .demo import seed, demo_loop
            seed(db)
            task = asyncio.create_task(demo_loop(db))
        yield
        if task:
            import asyncio
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        app.state.server_manager.stop()
        db.close()

    app = FastAPI(title="RaceCoach", version="0.1.0", lifespan=lifespan)
    app.state.db = db
    app.state.demo = demo
    app.state.data_dir = data_dir
    from .server_manager import ServerManager
    app.state.server_manager = ServerManager(data_dir)

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return Response("Niedozwolone źródło żądania", status_code=403)
            length = request.headers.get("content-length")
            if length and int(length) > 2_000_000:
                return Response("Zbyt duże żądanie", status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/meta")
    def meta():
        return {"demo": demo, "demo_login": {"email": "instruktor@demo.local", "password": "Trening2026!"} if demo else None}

    @app.post("/api/auth/login")
    def login(body: Login, request: Request, response: Response):
        key = request.client.host if request.client else "local"
        if not limiter.allow(key):
            raise HTTPException(429, "Zbyt wiele prób logowania. Spróbuj ponownie za 5 minut")
        account = db.one("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),))
        if not account or not password_matches(body.password, account["password_hash"]):
            raise HTTPException(401, "Niepoprawny e-mail lub hasło")
        token = new_token()
        with db.transaction() as c:
            c.execute("DELETE FROM auth_sessions WHERE expires<?", (time.time(),))
            c.execute("INSERT INTO auth_sessions VALUES (?,?,?)", (digest(token), account["id"], time.time() + 43200))
        response.set_cookie(COOKIE, token, max_age=43200, httponly=True, samesite="strict",
                            secure=os.getenv("RACECOACH_SECURE_COOKIES") == "1")
        return {k: account[k] for k in ("id", "email", "name", "role")}

    @app.get("/api/auth/me")
    def me(current=Depends(user)):
        return current

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with db.transaction() as c:
            c.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/trainees")
    def trainees(current=Depends(user)):
        condition = " WHERE u.id=?" if current["role"] == "trainee" else ""
        args = (current["id"],) if condition else ()
        return db.all("SELECT u.id,u.name,u.email,t.notes,u.created FROM trainees t JOIN users u ON t.user_id=u.id" + condition + " ORDER BY u.name", args)

    @app.post("/api/trainees", status_code=201)
    def create_trainee(body: TraineeCreate, actor=Depends(instructor)):
        row_id = uid()
        try:
            with db.transaction() as c:
                c.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (row_id, body.email, body.name, "trainee", password_hash(body.password), time.time()))
                c.execute("INSERT INTO trainees VALUES (?,?)", (row_id, body.notes))
                db.audit(actor["id"], "trainee.create", row_id, conn=c)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Konto o tym adresie już istnieje")
        return {"id": row_id, "name": body.name, "email": body.email, "notes": body.notes}

    @app.get("/api/plans")
    def plans(current=Depends(user)):
        query = "SELECT p.*,u.name AS trainee_name FROM plans p JOIN users u ON u.id=p.trainee_id"
        args = ()
        if current["role"] == "trainee":
            query += " WHERE p.trainee_id=?"
            args = (current["id"],)
        records = db.all(query + " ORDER BY p.created DESC", args)
        for p in records:
            p["items"] = db.all("SELECT * FROM plan_items WHERE plan_id=? ORDER BY sequence", (p["id"],))
            for item in p["items"]:
                item["criteria"] = json.loads(item["criteria"])
        return records

    @app.post("/api/plans", status_code=201)
    def create_plan(body: PlanCreate, actor=Depends(instructor)):
        if not db.one("SELECT user_id FROM trainees WHERE user_id=?", (body.trainee_id,)):
            raise HTTPException(404, "Nie znaleziono kursanta")
        row_id = uid()
        with db.transaction() as c:
            c.execute("INSERT INTO plans VALUES (?,?,?,?)", (row_id, body.trainee_id, body.title, time.time()))
            db.audit(actor["id"], "plan.create", row_id, body.model_dump(), c)
        return {"id": row_id}

    @app.post("/api/plans/{plan_id}/items", status_code=201)
    def add_item(plan_id: str, body: PlanItemCreate, actor=Depends(instructor)):
        require_row(db, "plans", plan_id)
        require_row(db, "exercises", body.exercise_id)
        row_id = uid()
        with db.transaction() as c:
            sequence = c.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM plan_items WHERE plan_id=?", (plan_id,)).fetchone()[0]
            c.execute("INSERT INTO plan_items(id,plan_id,exercise_id,title,goal,criteria,mode,sequence,scheduled) VALUES (?,?,?,?,?,?,?,?,?)",
                      (row_id, plan_id, body.exercise_id, body.title, body.goal, dump(body.criteria), body.mode, sequence, body.scheduled))
            db.audit(actor["id"], "plan.item.create", row_id, body.model_dump(), c)
        return {"id": row_id}

    @app.patch("/api/plan-items/{item_id}")
    def update_item(item_id: str, body: PlanItemUpdate, actor=Depends(instructor)):
        require_row(db, "plan_items", item_id)
        with db.transaction() as c:
            c.execute("UPDATE plan_items SET status=? WHERE id=?", (body.status, item_id))
            db.audit(actor["id"], "plan.item.status", item_id, body.model_dump(), c)
        return {"ok": True}

    @app.post("/api/stations", status_code=201)
    def pair_station(body: StationCreate, actor=Depends(instructor)):
        row_id, token = uid(), new_token()
        with db.transaction() as c:
            c.execute("INSERT INTO stations(id,name,token_hash,simulated,created) VALUES (?,?,?,?,?)", (row_id, body.name, digest(token), 0, time.time()))
            db.audit(actor["id"], "station.pair", row_id, conn=c)
        return {"id": row_id, "name": body.name, "token": token}

    @app.get("/api/stations")
    def list_stations(actor=Depends(instructor)):
        records = db.all("SELECT id,name,simulated,last_seen,state FROM stations ORDER BY name")
        for row in records:
            row["state"] = json.loads(row["state"])
            row["online"] = row["last_seen"] is not None and time.time() - row["last_seen"] < 12
            row["attempt"] = db.one("SELECT a.id,a.trainee_id,u.name AS trainee_name,a.run_id FROM attempts a JOIN users u ON u.id=a.trainee_id WHERE a.station_id=? AND a.status IN ('preparing','running','stopping') ORDER BY a.created DESC LIMIT 1", (row["id"],))
        return records

    @app.get("/api/commands")
    def commands(actor=Depends(instructor)):
        rows = db.all("SELECT c.*,s.name AS station_name FROM commands c JOIN stations s ON s.id=c.station_id ORDER BY c.created DESC LIMIT 100")
        for row in rows:
            row["payload"] = json.loads(row["payload"])
            row["result"] = json.loads(row["result"])
        return rows

    @app.get("/api/audit")
    def audit(actor=Depends(instructor)):
        rows = db.all("SELECT * FROM audit ORDER BY created DESC LIMIT 100")
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        return rows

    # Feature routers are registered before the built frontend fallback.
    from .routes import register_routes
    register_routes(app, db)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="panel")
    return app
