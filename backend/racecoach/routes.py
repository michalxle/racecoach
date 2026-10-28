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


def register_routes(app, db):
    @app.post("/api/agent/heartbeat")
    def heartbeat(body: Heartbeat, source=Depends(station)):
        with db.transaction() as c:
            c.execute("UPDATE stations SET last_seen=?,state=? WHERE id=?", (time.time(), dump(body.model_dump()), source["id"]))
        return {"server_time": time.time()}

    @app.get("/api/agent/commands")
    def poll_commands(source=Depends(station)):
        with db.transaction() as c:
            expired = c.execute("SELECT * FROM commands WHERE station_id=? AND status IN ('queued','accepted','running') AND expires<?", (source["id"], time.time())).fetchall()
            for row in expired:
                c.execute("UPDATE commands SET status='expired',result=? WHERE id=?", (dump({"error": "Minął termin wykonania; stan wymaga uzgodnienia"}), row["id"]))
                payload = json.loads(row["payload"])
                if row["kind"] in ("prepare_session", "start_session"):
                    c.execute("UPDATE attempts SET status='failed' WHERE id=? AND status IN ('preparing','running')", (payload.get("attempt_id"),))
                    c.execute("UPDATE runs SET status='attention' WHERE id=? AND status NOT IN ('completed','interrupted')", (payload.get("run_id"),))
            rows = c.execute("SELECT * FROM commands WHERE station_id=? AND status IN ('queued','accepted','running') ORDER BY created LIMIT 20", (source["id"],)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]), "result": json.loads(row["result"])} for row in rows]

    @app.post("/api/agent/commands/{command_id}/result")
    def command_result(command_id: str, body: CommandResult, source=Depends(station)):
        apply_command_result(db, source["id"], command_id, body.status, body.result)
        return {"ok": True}


def apply_command_result(db, station_id, command_id, status, result):
    with db.transaction() as c:
        raw = c.execute("SELECT * FROM commands WHERE id=? AND station_id=?", (command_id, station_id)).fetchone()
        if not raw:
            raise HTTPException(404, "Nie znaleziono polecenia tego stanowiska")
        row = dict(raw)
        if row["status"] == status and (status in TERMINAL or json.loads(row["result"]) == result):
            return
        if row["status"] in TERMINAL or status not in TRANSITIONS.get(row["status"], set()):
            raise HTTPException(409, "Niedozwolona zmiana stanu polecenia")
        if time.time() > row["expires"]:
            raise HTTPException(409, "Polecenie wygasło; wymagane uzgodnienie stanu")
        payload = json.loads(row["payload"])
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
