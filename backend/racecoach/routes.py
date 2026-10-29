from __future__ import annotations

import json
import time

from fastapi import Depends, HTTPException

from .app import station
from .db import dump
from .models import CommandResult, Heartbeat

TERMINAL = {"succeeded", "failed", "rejected", "unknown", "expired"}
TRANSITIONS = {
    "queued": {"accepted", "running", "succeeded", "failed", "rejected", "unknown"},
    "accepted": {"running", "succeeded", "failed", "rejected", "unknown"},
    "running": {"succeeded", "failed", "rejected", "unknown"},
}


def expire_commands(db):
    """Expire centrally even if an agent is offline; preserve uncertain reservations."""
    with db.transaction() as c:
        expired = c.execute("SELECT * FROM commands WHERE status IN ('queued','accepted','running') AND expires<?", (time.time(),)).fetchall()
        for row in expired:
            result = {"error": "Minął termin wykonania; rzeczywisty stan wymaga uzgodnienia"}
            c.execute("UPDATE commands SET status='expired',result=? WHERE id=?", (dump(result), row["id"]))
            payload = json.loads(row["payload"])
            if row["kind"] in ("prepare_session", "start_session", "stop_session"):
                c.execute("UPDATE attempts SET status='attention' WHERE id=? AND status NOT IN ('completed','interrupted')", (payload.get("attempt_id"),))
                c.execute("UPDATE runs SET status='attention' WHERE id=? AND status NOT IN ('completed','interrupted')", (payload.get("run_id"),))
            db.audit("system", "command.expired", row["id"], result, c)


def register_routes(app, db):
    @app.post("/api/agent/heartbeat")
    def heartbeat(body: Heartbeat, source=Depends(station)):
        with db.transaction() as c:
            c.execute("UPDATE stations SET last_seen=?,state=? WHERE id=?", (time.time(), dump(body.model_dump()), source["id"]))
        row = db.one("SELECT content,overlay FROM stations WHERE id=?", (source["id"],))
        # Agent porównuje skrót katalogu i wysyła go ponownie, gdy centrala go nie ma (np. nowa baza).
        return {"server_time": time.time(), "content_hash": json.loads(row["content"] or "{}").get("hash"),
                "overlay": json.loads(row["overlay"] or "{}"), "rivals": rivals(db, source["id"])}

    @app.get("/api/agent/commands")
    def poll_commands(source=Depends(station)):
        expire_commands(db)
        with db.transaction() as c:
            rows = c.execute("SELECT * FROM commands WHERE station_id=? AND status IN ('queued','accepted','running') ORDER BY created LIMIT 20", (source["id"],)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]), "result": json.loads(row["result"])} for row in rows]

    @app.post("/api/agent/commands/{command_id}/result")
    def command_result(command_id: str, body: CommandResult, source=Depends(station)):
        apply_command_result(db, source["id"], command_id, body.status, body.result)
        return {"ok": True}

    from .training import register_training_routes
    register_training_routes(app, db)
    from .content import register_content_routes
    register_content_routes(app, db)
    from .coaching import register_coaching_routes, register_overlay_routes
    register_coaching_routes(app, db)
    register_overlay_routes(app, db)


def rivals(db, station_id):
    """Pozycje pozostałych uczestników tej samej sesji (do minimapy w grze), z ostatniego heartbeatu."""
    own = db.one("SELECT a.run_id,r.scenario FROM attempts a JOIN runs r ON r.id=a.run_id WHERE a.station_id=? "
                 "AND a.status IN ('ready','running') ORDER BY a.created DESC LIMIT 1", (station_id,))
    if not own or not json.loads(own["scenario"]).get("show_rivals", True):
        return []
    result = []
    for other in db.all("SELECT a.station_id,u.name,s.state,s.last_seen FROM attempts a JOIN users u ON u.id=a.trainee_id "
                        "JOIN stations s ON s.id=a.station_id WHERE a.run_id=? AND a.station_id!=? AND a.status='running'",
                        (own["run_id"], station_id)):
        live = json.loads(other["state"]).get("telemetry") or {}
        if other["last_seen"] and time.time() - other["last_seen"] < 5 and live.get("x") is not None and live.get("z") is not None:
            result.append({"name": other["name"], "x": live["x"], "z": live["z"], "progress": live.get("progress"),
                           "lap": live.get("lap")})
    return result


def apply_command_result(db, station_id, command_id, status, result):
    with db.transaction() as c:
        raw = c.execute("SELECT * FROM commands WHERE id=? AND station_id=?", (command_id, station_id)).fetchone()
        if not raw:
            raise HTTPException(404, "Nie znaleziono polecenia tego stanowiska")
        row = dict(raw)
        if row["status"] == status:
            if json.loads(row["result"]) != result:
                raise HTTPException(409, "Powtórzony wynik polecenia zawiera inne dane")
            return
        if row["status"] in TERMINAL or status not in TRANSITIONS.get(row["status"], set()):
            raise HTTPException(409, "Niedozwolona zmiana stanu polecenia")
        if time.time() > row["expires"]:
            raise HTTPException(409, "Polecenie wygasło; wymagane uzgodnienie stanu")
        payload = json.loads(row["payload"])
        if row["kind"] == "prepare_session" and status == "succeeded" and result.get("verified") is not True:
            raise HTTPException(422, "Agent nie potwierdził weryfikacji scenariusza")
        if row["kind"] in ("prepare_session", "start_session") and status == "succeeded":
            run = c.execute("SELECT status FROM runs WHERE id=?", (payload["run_id"],)).fetchone()
            permitted = ("preparing", "ready") if row["kind"] == "prepare_session" else ("starting", "running")
            if not run or run["status"] not in permitted:
                raise HTTPException(409, "Sesja została anulowana lub wymaga uzgodnienia; spóźniony start nie jest przyjmowany")
            profile = payload["scenario"].get("hardware_profile")
            if profile:
                hardware = result.get("hardware", {}).get("actual", {}) if row["kind"] == "prepare_session" else result.get("actual", {}).get("hardware", {})
                if any(hardware.get(k) != profile[k] for k in ("degrees", "strength")):
                    raise HTTPException(422, "Agent nie potwierdził profilu sprzętu wymaganego w ćwiczeniu")
        if row["kind"] == "start_session" and status == "succeeded":
            expected = payload["scenario"]
            actual = result.get("actual", {})
            if any(actual.get(k) != expected.get(k) for k in ("track_id", "layout", "car")):
                raise HTTPException(422, "Gra nie potwierdziła oczekiwanego toru, layoutu i auta")
            if actual.get("simulated") != bool(db.one("SELECT simulated FROM stations WHERE id=?", (station_id,))["simulated"]):
                raise HTTPException(422, "Niezgodność trybu demonstracyjnego")
        if row["kind"] == "hardware_profile" and status == "succeeded":
            actual = result.get("actual", {})
            if any(actual.get(k) != payload[k] for k in ("degrees", "strength")):
                raise HTTPException(422, "Profil nie został potwierdzony odczytem zwrotnym")
        c.execute("UPDATE commands SET status=?,result=? WHERE id=?", (status, dump(result), command_id))
        if row["kind"] in ("prepare_session", "start_session") and status in TERMINAL:
            attempt_id, run_id = payload["attempt_id"], payload["run_id"]
            if status != "succeeded":
                c.execute("UPDATE attempts SET status='failed' WHERE id=?", (attempt_id,))
                c.execute("UPDATE runs SET status='attention' WHERE id=?", (run_id,))
            elif row["kind"] == "prepare_session":
                c.execute("UPDATE attempts SET status='ready' WHERE id=? AND status='preparing'", (attempt_id,))
                remaining = c.execute("SELECT COUNT(*) FROM commands WHERE kind='prepare_session' AND json_extract(payload,'$.run_id')=? AND status!='succeeded'", (run_id,)).fetchone()[0]
                if not remaining:
                    c.execute("UPDATE runs SET status='ready' WHERE id=? AND status='preparing'", (run_id,))
            else:
                c.execute("UPDATE attempts SET status='running',config=? WHERE id=?", (dump(result.get("actual", {})), attempt_id))
                c.execute("UPDATE runs SET status='running' WHERE id=? AND status IN ('starting','running')", (run_id,))
                item = c.execute("SELECT plan_item_id FROM attempts WHERE id=?", (attempt_id,)).fetchone()[0]
                if item:
                    c.execute("UPDATE plan_items SET status='running' WHERE id=?", (item,))
        db.audit(station_id, "command." + status, command_id, result, c)
