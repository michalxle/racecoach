from __future__ import annotations

import json
import time

from fastapi import Depends, HTTPException, Query

from .app import instructor, require_row, station, user
from .db import dump, uid
from .models import (AttemptFinish, AttemptReview, ExerciseCreate, ExerciseReference, HardwareProfile,
                     RunCreate, TelemetryBatch, TrackCreate, WeatherChange)
from .telemetry import analyze, load_samples, select_lap, split_laps, store_chunk


def enqueue(c, station_id, kind, payload, ttl=90):
    command_id = uid()
    c.execute("INSERT INTO commands VALUES (?,?,?,?,?,?,?,?)",
              (command_id, station_id, kind, dump(payload), "queued", time.time(), time.time() + ttl, "{}"))
    return command_id


def decode_track(row):
    return {**row, "geometry": json.loads(row["geometry"]), "sections": json.loads(row["sections"])}


def can_read_attempt(db, attempt_id, actor):
    row = require_row(db, "attempts", attempt_id)
    shared_reference = db.one("SELECT exercise_id FROM exercise_references WHERE attempt_id=?", (attempt_id,))
    if actor["role"] == "trainee" and row["trainee_id"] != actor["id"] and not shared_reference:
        raise HTTPException(403, "Brak dostępu do przejazdu innego kursanta")
    return row


def finish_attempt(db, attempt_id, status, config, note):
    with db.transaction() as c:
        row = c.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if row["status"] in ("completed", "interrupted", "failed"):
            return
        confirmed = {**json.loads(row["config"]), **config}
        c.execute("UPDATE attempts SET status=?,config=?,note=? WHERE id=?", (status, dump(confirmed), note, attempt_id))
        if row["plan_item_id"]:
            c.execute("UPDATE plan_items SET status='ready' WHERE id=? AND status='running'", (row["plan_item_id"],))
        active = c.execute("SELECT COUNT(*) FROM attempts WHERE run_id=? AND status IN ('preparing','ready','running','stopping','attention')", (row["run_id"],)).fetchone()[0]
        if not active:
            failed = c.execute("SELECT COUNT(*) FROM attempts WHERE run_id=? AND status!='completed'", (row["run_id"],)).fetchone()[0]
            c.execute("UPDATE runs SET status=?,ended=? WHERE id=?", ("interrupted" if failed else "completed", time.time(), row["run_id"]))


def register_training_routes(app, db):
    @app.get("/api/tracks")
    def tracks(actor=Depends(user)):
        return [decode_track(row) for row in db.all("SELECT * FROM tracks ORDER BY name")]

    @app.post("/api/tracks", status_code=201)
    def add_track(body: TrackCreate, actor=Depends(instructor)):
        if db.one("SELECT id FROM tracks WHERE id=?", (body.id,)):
            raise HTTPException(409, "Ta wersja toru już istnieje; nadaj nowy identyfikator")
        with db.transaction() as c:
            c.execute("INSERT INTO tracks(id,name,layout,length,geometry,sections,version,source,game_id) VALUES (?,?,?,?,?,?,?,?,?)",
                      (body.id, body.name, body.layout, body.length, dump(body.geometry), dump([s.model_dump() for s in body.sections]), body.version, body.source, body.game_id or body.id))
            db.audit(actor["id"], "track.import", body.id, {"version": body.version}, c)
        return {"id": body.id}

    @app.get("/api/exercises")
    def exercises(actor=Depends(user)):
        rows = db.all("SELECT e.*,t.name AS track_name,t.layout FROM exercises e JOIN tracks t ON t.id=e.track_id ORDER BY e.title")
        for row in rows:
            row["conditions"] = json.loads(row["conditions"])
            row["hardware_profile"] = json.loads(row["hardware_profile"]) if row["hardware_profile"] else None
            row["reference"] = db.one("SELECT attempt_id,lap FROM exercise_references WHERE exercise_id=?", (row["id"],))
        return rows

    @app.post("/api/exercises", status_code=201)
    def add_exercise(body: ExerciseCreate, actor=Depends(instructor)):
        require_row(db, "tracks", body.track_id)
        row_id = uid()
        with db.transaction() as c:
            c.execute("INSERT INTO exercises(id,title,track_id,car,conditions,duration,mode,revision,hardware_profile) VALUES (?,?,?,?,?,?,?,?,?)", (row_id, body.title, body.track_id, body.car, dump(body.conditions.model_dump()), body.duration, body.mode, 1, dump(body.hardware_profile.model_dump()) if body.hardware_profile else None))
            db.audit(actor["id"], "exercise.create", row_id, body.model_dump(), c)
        return {"id": row_id}

    @app.post("/api/exercises/{exercise_id}/reference")
    def set_reference(exercise_id: str, body: ExerciseReference, actor=Depends(instructor)):
        require_row(db, "exercises", exercise_id)
        attempt = require_row(db, "attempts", body.attempt_id)
        run = require_row(db, "runs", attempt["run_id"])
        if run["exercise_id"] != exercise_id or attempt["status"] not in ("completed", "interrupted"):
            raise HTTPException(422, "Wzorzec musi być zakończoną próbą tego ćwiczenia")
        select_lap(split_laps(load_samples(db, body.attempt_id)), body.lap)
        with db.transaction() as c:
            c.execute("INSERT OR REPLACE INTO exercise_references VALUES (?,?,?,?,?)", (exercise_id, body.attempt_id, body.lap, actor["id"], time.time()))
            db.audit(actor["id"], "exercise.reference", exercise_id, body.model_dump(), c)
        return {"ok": True}

    @app.get("/api/runs")
    def runs(actor=Depends(instructor)):
        rows = db.all("SELECT r.*,e.title FROM runs r JOIN exercises e ON e.id=r.exercise_id ORDER BY r.created DESC LIMIT 100")
        for row in rows:
            row["scenario"] = json.loads(row["scenario"])
            row["scenario"].pop("connection", None)
            row["participants"] = db.all("SELECT a.id,a.status,a.station_id,a.trainee_id,u.name AS trainee_name,s.name AS station_name FROM attempts a JOIN users u ON u.id=a.trainee_id JOIN stations s ON s.id=a.station_id WHERE a.run_id=?", (row["id"],))
        return rows

    @app.post("/api/runs", status_code=201)
    def create_run(body: RunCreate, actor=Depends(instructor)):
        exercise = require_row(db, "exercises", body.exercise_id)
        track = decode_track(require_row(db, "tracks", exercise["track_id"]))
        if exercise["mode"] not in (body.mode, "either"):
            raise HTTPException(422, "Ćwiczenie nie obsługuje tego trybu")
        scenario = {"exercise_id": exercise["id"], "revision": exercise["revision"], "track_key": track["id"],
                    "track_id": track["game_id"], "layout": track["layout"], "track": track, "car": exercise["car"],
                    "conditions": json.loads(exercise["conditions"]), "duration": exercise["duration"], "mode": body.mode,
                    "hardware_profile": json.loads(exercise["hardware_profile"]) if exercise["hardware_profile"] else None}
        sources = []
        for p in body.participants:
            source = require_row(db, "stations", p.station_id)
            if not db.one("SELECT user_id FROM trainees WHERE user_id=?", (p.trainee_id,)):
                raise HTTPException(404, "Nie znaleziono kursanta")
            if not source["last_seen"] or time.time() - source["last_seen"] > 12:
                raise HTTPException(409, "Stanowisko " + source["name"] + " jest offline")
            state = json.loads(source["state"])
            if state.get("game") != "idle":
                raise HTTPException(409, "Stanowisko musi być bezczynne")
            if p.plan_item_id:
                item = require_row(db, "plan_items", p.plan_item_id)
                plan = require_row(db, "plans", item["plan_id"])
                if plan["trainee_id"] != p.trainee_id or item["exercise_id"] != exercise["id"] or item["mode"] not in (body.mode, "either"):
                    raise HTTPException(422, "Pozycja planu nie pasuje do kursanta, ćwiczenia lub trybu")
                if item["status"] in ("passed", "skipped"):
                    raise HTTPException(409, "Pozycja planu jest zamknięta; zmień status przed kolejną próbą")
            if not source["simulated"]:
                required = {f"track:{track['game_id']}:{track['layout']}", "car:" + exercise["car"]}
                if not required.issubset(state.get("catalog", [])):
                    raise HTTPException(409, "Stanowisko nie potwierdziło wymaganej zawartości")
            sources.append(source)
        if len({s["simulated"] for s in sources}) > 1:
            raise HTTPException(422, "Sesja nie może łączyć stanowisk demo i rzeczywistych")
        if bool(sources[0]["simulated"]) != (track["source"] == "demo"):
            raise HTTPException(422, "Tor demonstracyjny jest dostępny wyłącznie w demo")
        run_id = uid()
        with db.transaction() as c:
            # The lock and transaction keep double-clicks and concurrent instructors from reserving a station twice.
            for p in body.participants:
                busy = c.execute("SELECT id FROM attempts WHERE (station_id=? OR trainee_id=?) AND status IN ('preparing','ready','running','stopping','attention')", (p.station_id, p.trainee_id)).fetchone()
                if busy:
                    raise HTTPException(409, "Stanowisko lub kursant ma już aktywną próbę")
            if body.mode == "multiplayer" and not sources[0]["simulated"]:
                other = c.execute("SELECT r.id FROM runs r JOIN attempts a ON a.run_id=r.id JOIN stations s ON s.id=a.station_id WHERE r.mode='multiplayer' AND s.simulated=0 AND r.status NOT IN ('completed','interrupted') LIMIT 1").fetchone()
                if other:
                    raise HTTPException(409, "Zarządzany serwer ma już aktywną lub nieuzgodnioną sesję grupową")
                try:
                    scenario["connection"] = app.state.server_manager.start(run_id, scenario, body.participants)
                except (RuntimeError, OSError) as exc:
                    raise HTTPException(409, str(exc))
            c.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (run_id, body.mode, exercise["id"], dump(scenario), "preparing", time.time(), None))
            attempts = []
            for p in body.participants:
                attempt_id = uid()
                c.execute("INSERT INTO attempts(id,run_id,trainee_id,station_id,plan_item_id,status,created) VALUES (?,?,?,?,?,?,?)", (attempt_id, run_id, p.trainee_id, p.station_id, p.plan_item_id, "preparing", time.time()))
                enqueue(c, p.station_id, "prepare_session", {"run_id": run_id, "attempt_id": attempt_id, "scenario": scenario}, ttl=120)
                attempts.append(attempt_id)
            db.audit(actor["id"], "run.prepare", run_id, {"attempts": attempts}, c)
        return {"id": run_id, "attempts": attempts, "status": "preparing"}

    @app.post("/api/runs/{run_id}/start")
    def start_run(run_id: str, actor=Depends(instructor)):
        with db.transaction() as c:
            run = require_row(db, "runs", run_id)
            if run["status"] != "ready":
                raise HTTPException(409, "Wszystkie stanowiska muszą najpierw potwierdzić przygotowanie")
            participants = db.all("SELECT * FROM attempts WHERE run_id=?", (run_id,))
            for p in participants:
                source = require_row(db, "stations", p["station_id"])
                if not source["last_seen"] or time.time() - source["last_seen"] > 12:
                    raise HTTPException(409, "Uczestnik utracił połączenie")
            scenario = json.loads(run["scenario"])
            for p in participants:
                enqueue(c, p["station_id"], "start_session", {"run_id": run_id, "attempt_id": p["id"], "scenario": scenario}, ttl=120)
            c.execute("UPDATE runs SET status='starting' WHERE id=?", (run_id,))
            db.audit(actor["id"], "run.start", run_id, conn=c)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str, actor=Depends(instructor)):
        with db.transaction() as c:
            run = require_row(db, "runs", run_id)
            if run["status"] in ("completed", "interrupted"):
                return {"ok": True}
            for p in db.all("SELECT * FROM attempts WHERE run_id=? AND status NOT IN ('completed','interrupted')", (run_id,)):
                enqueue(c, p["station_id"], "stop_session", {"run_id": run_id, "attempt_id": p["id"]})
                c.execute("UPDATE attempts SET status='stopping' WHERE id=?", (p["id"],))
            c.execute("UPDATE commands SET status='rejected',result=? WHERE kind IN ('start_session','prepare_session') AND json_extract(payload,'$.run_id')=? AND status IN ('queued','accepted')", (dump({"error": "Anulowane przez instruktora"}), run_id))
            c.execute("UPDATE runs SET status='stopping' WHERE id=?", (run_id,))
            db.audit(actor["id"], "run.stop", run_id, conn=c)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/weather")
    def weather(run_id: str, body: WeatherChange, actor=Depends(instructor)):
        run = require_row(db, "runs", run_id)
        if run["status"] != "running":
            raise HTTPException(409, "Zmiana pogody wymaga trwającej sesji")
        participants = db.all("SELECT s.simulated FROM attempts a JOIN stations s ON s.id=a.station_id WHERE a.run_id=?", (run_id,))
        if not all(p["simulated"] for p in participants):
            try:
                actual = app.state.server_manager.weather(run_id, body.model_dump())
            except Exception as exc:
                db.audit(actor["id"], "weather.failed", run_id, {"error": str(exc)})
                raise HTTPException(409, "Most pogodowy nie potwierdził zmiany. Sprawdź konfigurację i dziennik")
        else:
            actual = {"confirmed": True, "simulated": True, **body.model_dump()}
        db.audit(actor["id"], "weather.changed", run_id, actual)
        return actual

    @app.post("/api/stations/{station_id}/profile")
    def profile(station_id: str, body: HardwareProfile, actor=Depends(instructor)):
        source = require_row(db, "stations", station_id)
        state = json.loads(source["state"])
        if not source["last_seen"] or time.time() - source["last_seen"] > 12 or state.get("game") != "idle":
            raise HTTPException(409, "Zmiana profilu wymaga bezczynnego stanowiska online")
        if "hardware.profile" not in state.get("capabilities", []):
            raise HTTPException(409, "Agent nie udostępnia konfiguracji sprzętu")
        with db.transaction() as c:
            if c.execute("SELECT id FROM attempts WHERE station_id=? AND status IN ('preparing','ready','running','stopping','attention')", (station_id,)).fetchone():
                raise HTTPException(409, "Stanowisko jest zarezerwowane do sesji")
            command = enqueue(c, station_id, "hardware_profile", body.model_dump())
            db.audit(actor["id"], "hardware.profile", station_id, body.model_dump(), c)
        return {"command_id": command, "status": "queued"}

    @app.get("/api/attempts")
    def attempts(actor=Depends(user)):
        query = "SELECT a.*,u.name AS trainee_name,s.name AS station_name,e.title AS exercise_title,r.mode,r.scenario FROM attempts a JOIN users u ON u.id=a.trainee_id JOIN stations s ON s.id=a.station_id JOIN runs r ON r.id=a.run_id JOIN exercises e ON e.id=r.exercise_id"
        args = ()
        if actor["role"] == "trainee":
            query += " WHERE (a.trainee_id=? OR a.id IN (SELECT attempt_id FROM exercise_references))"
            args = (actor["id"],)
        rows = db.all(query + " ORDER BY a.created DESC LIMIT 200", args)
        for row in rows:
            for key in ("config", "result", "scenario"):
                row[key] = json.loads(row[key])
            row["scenario"].pop("connection", None)
            row["sample_count"] = db.one("SELECT COALESCE(SUM(count),0) AS n FROM telemetry_chunks WHERE attempt_id=?", (row["id"],))["n"]
            if actor["role"] == "trainee" and row["trainee_id"] != actor["id"]:
                row.update(trainee_id="reference", trainee_name="Wzorzec instruktora", station_name="Stanowisko wzorca", plan_item_id=None, note="", result={})
        return rows

    @app.get("/api/attempts/{attempt_id}/laps")
    def laps(attempt_id: str, actor=Depends(user)):
        can_read_attempt(db, attempt_id, actor)
        return [{k: v for k, v in lap.items() if k != "points"} for lap in split_laps(load_samples(db, attempt_id))]

    @app.get("/api/attempts/{attempt_id}/analysis")
    def analysis(attempt_id: str, reference_id: str | None = None, lap: int | None = None,
                 reference_lap: int | None = None, actor=Depends(user)):
        own = can_read_attempt(db, attempt_id, actor)
        target = can_read_attempt(db, reference_id or attempt_id, actor)
        a = json.loads(require_row(db, "runs", own["run_id"])["scenario"])
        b = json.loads(require_row(db, "runs", target["run_id"])["scenario"])
        if any(a.get(k) != b.get(k) for k in ("track_key", "layout")) or a["track"]["version"] != b["track"]["version"]:
            raise HTTPException(422, "Porównanie wymaga tego samego toru, layoutu i wersji sekcji")
        warnings = []
        for key, label in (("car", "Różne samochody"), ("conditions", "Różne warunki początkowe")):
            if a[key] != b[key]:
                warnings.append(label)
        if own["config"] != target["config"]:
            warnings.append("Różnice lub niepełna zgodność zapisanej konfiguracji klientów")
        events = db.one("SELECT id FROM audit WHERE action='weather.changed' AND target IN (?,?) LIMIT 1", (own["run_id"], target["run_id"]))
        if events:
            warnings.append("Warunki zmieniały się podczas jazdy; sprawdź dziennik pogody")
        current = select_lap(split_laps(load_samples(db, attempt_id)), lap)
        reference = select_lap(split_laps(load_samples(db, reference_id or attempt_id)), reference_lap)
        return {**analyze(current, reference, a["track"]["sections"], a["track"]["length"]), "track": a["track"],
                "warnings": warnings, "attempt_id": attempt_id, "reference_id": reference_id or attempt_id,
                "simulated": a["track"]["source"] == "demo"}

    @app.get("/api/attempts/{attempt_id}/export")
    def export(attempt_id: str, actor=Depends(user)):
        record = can_read_attempt(db, attempt_id, actor)
        scenario = json.loads(require_row(db, "runs", record["run_id"])["scenario"])
        scenario.pop("connection", None)
        return {"schema": "racecoach.telemetry.v1", "attempt_id": attempt_id, "scenario": scenario,
                "config": json.loads(record["config"]), "samples": load_samples(db, attempt_id)}

    @app.post("/api/attempts/{attempt_id}/review")
    def review(attempt_id: str, body: AttemptReview, actor=Depends(instructor)):
        record = require_row(db, "attempts", attempt_id)
        if record["status"] not in ("completed", "interrupted", "failed"):
            raise HTTPException(409, "Ocena wymaga zakończenia próby")
        with db.transaction() as c:
            result = {"decision": body.decision, "reviewer": actor["id"], "reviewed_at": time.time()}
            c.execute("UPDATE attempts SET note=?,result=? WHERE id=?", (body.note, dump(result), attempt_id))
            if record["plan_item_id"] and body.decision != "none":
                c.execute("UPDATE plan_items SET status=? WHERE id=?", (body.decision, record["plan_item_id"]))
            db.audit(actor["id"], "attempt.review", attempt_id, body.model_dump(), c)
        return {"ok": True}

    @app.post("/api/agent/attempts/{attempt_id}/telemetry")
    def ingest(attempt_id: str, body: TelemetryBatch, source=Depends(station)):
        record = require_row(db, "attempts", attempt_id)
        if record["station_id"] != source["id"]:
            raise HTTPException(403, "Próba należy do innego stanowiska")
        # Delayed uploads are accepted after completion so an offline buffer can drain.
        inserted = store_chunk(db, attempt_id, body.chunk_id, [s.model_dump() for s in body.samples])
        return {"ok": True, "inserted": inserted, "last_seq": body.samples[-1].seq}

    @app.post("/api/agent/attempts/{attempt_id}/finish")
    def finish(attempt_id: str, body: AttemptFinish, source=Depends(station)):
        record = require_row(db, "attempts", attempt_id)
        if record["station_id"] != source["id"]:
            raise HTTPException(403, "Próba należy do innego stanowiska")
        finish_attempt(db, attempt_id, body.status, body.config, body.note)
        run = require_row(db, "runs", record["run_id"])
        if run["status"] in ("completed", "interrupted"):
            app.state.server_manager.stop(run["id"])
        return {"ok": True}
