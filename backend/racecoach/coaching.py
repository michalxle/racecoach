"""Okrążenia od trenera na stanowisku, wzorce do delty, wyścig, rankingi, rekordy i osiągnięcia.

Agent wysyła po każdym okrążeniu: czas z gry, ważność (wyjazd >2 kołami, boks), wskazówki
i przebieg ważnego okrążenia (500 punktów wzdłuż toru). Centrala z nich buduje rekordy,
rankingi auto+tor, klasyfikację wyścigu i wybiera wzorzec dla kolejnej sesji kursanta.
"""
from __future__ import annotations

import json
import math
import time

from fastapi import Depends, HTTPException, Query

from .app import instructor, require_row, station, user
from .db import dump
from .models import LapEvent, MessageIn, OverlayLayout
from .telemetry import load_samples, split_laps

TRACE_POINTS = 500


def trace_from_points(points, n=TRACE_POINTS):
    """Okrążenie z telemetrii centrali → przebieg w formacie trenera (Trace.to_dict agenta)."""
    if len(points) < 10:
        return None
    start = points[0]["t"]
    time_ms = int(round((points[-1]["t"] - start) * 1000))
    out = {k: [] for k in ("t", "v", "g", "b", "x", "z")}
    j = 0
    for i in range(n):
        target = i / n
        while j < len(points) - 2 and points[j + 1]["progress"] < target:
            j += 1
        a, b = points[j], points[j + 1]
        span = b["progress"] - a["progress"]
        f = 0.0 if span <= 0 else min(1.0, max(0.0, (target - a["progress"]) / span))
        mix = lambda key: a[key] + (b[key] - a[key]) * f  # noqa: E731
        out["t"].append(int(round((mix("t") - start) * 1000)))
        out["v"].append(round(mix("speed"), 1))
        out["g"].append(round(mix("throttle"), 2))
        out["b"].append(round(mix("brake"), 2))
        out["x"].append(round(mix("x"), 1))
        out["z"].append(round(mix("z"), 1))
    length = sum(math.hypot(out["x"][(i + 1) % n] - out["x"][i], out["z"][(i + 1) % n] - out["z"][i]) for i in range(n))
    return {"n": n, "time_ms": time_ms, "len_m": round(length, 1), **out, "meta": {}}


def exercise_reference(db, exercise_id):
    row = db.one("SELECT attempt_id,lap FROM exercise_references WHERE exercise_id=?", (exercise_id,))
    if not row:
        return None
    lap = next((l for l in split_laps(load_samples(db, row["attempt_id"])) if l["lap"] == row["lap"] and l["usable"]), None)
    trace = trace_from_points(lap["points"]) if lap else None
    return {"source": "exercise", "trace": trace} if trace else None


def personal_best(db, trainee_id, exercise_id):
    return db.one("SELECT l.time_ms,l.trace IS NOT NULL AS has_trace,l.attempt_id,l.lap_no FROM laps l JOIN attempts a ON a.id=l.attempt_id "
                  "JOIN runs r ON r.id=a.run_id WHERE a.trainee_id=? AND r.exercise_id=? AND l.valid=1 ORDER BY l.time_ms LIMIT 1",
                  (trainee_id, exercise_id))


def coach_payload(db, attempt, run, exercise):
    """Dane trenera do polecenia start_session: wzorzec, rekord, opis sesji do nakładek."""
    trainee = db.one("SELECT name FROM users WHERE id=?", (attempt["trainee_id"],))
    item = db.one("SELECT title,goal FROM plan_items WHERE id=?", (attempt["plan_item_id"],)) if attempt["plan_item_id"] else None
    scenario = json.loads(run["scenario"])
    pb = personal_best(db, attempt["trainee_id"], exercise["id"])
    reference = exercise_reference(db, exercise["id"])
    if reference is None and pb and pb["has_trace"]:
        row = db.one("SELECT trace FROM laps WHERE attempt_id=? AND lap_no=?", (pb["attempt_id"], pb["lap_no"]))
        reference = {"source": "pb", "trace": json.loads(row["trace"])}
    station_row = db.one("SELECT content FROM stations WHERE id=?", (attempt["station_id"],))
    content = json.loads(station_row["content"] or "{}") if station_row else {}
    car = next((c["name"] for c in content.get("cars", []) if c["id"] == scenario["car"]), scenario["car"])
    track = next((t["name"] for t in content.get("tracks", []) if t["id"] == scenario["track_id"] and t.get("layout", "") == scenario["layout"]),
                 scenario["track"]["name"])
    return {"reference": reference, "pb_ms": pb["time_ms"] if pb else None, "race_laps": scenario.get("race_laps"),
            "info": {"trainee": trainee["name"] if trainee else "", "exercise": exercise["title"], "car": car, "track": track,
                     "goal": item["goal"] if item else "", "plan_item": item["title"] if item else "",
                     "duration": scenario["duration"], "race_laps": scenario.get("race_laps")}}


def classification(db, run_id, race_laps):
    rows = db.all("SELECT a.id,a.trainee_id,a.status,u.name AS trainee_name,s.name AS station_name FROM attempts a "
                  "JOIN users u ON u.id=a.trainee_id JOIN stations s ON s.id=a.station_id WHERE a.run_id=?", (run_id,))
    result = []
    for row in rows:
        laps = db.all("SELECT lap_no,time_ms,valid FROM laps WHERE attempt_id=? ORDER BY lap_no", (row["id"],))
        counted = laps[:race_laps] if race_laps else laps
        valid = [l["time_ms"] for l in counted if l["valid"]]
        result.append({"attempt_id": row["id"], "trainee_id": row["trainee_id"], "trainee_name": row["trainee_name"], "station_name": row["station_name"],
                       "laps": len(counted), "total_ms": sum(l["time_ms"] for l in counted),
                       "best_ms": min(valid) if valid else None, "finished": bool(race_laps) and len(counted) >= race_laps})
    result.sort(key=lambda r: (not r["finished"], -r["laps"], r["total_ms"]))
    leader = result[0] if result else None
    for position, row in enumerate(result, 1):
        row["position"] = position
        row["gap_ms"] = row["total_ms"] - leader["total_ms"] if leader and row["laps"] == leader["laps"] else None
    return result


COMBO = ("json_extract(r.scenario,'$.track_id')", "json_extract(r.scenario,'$.layout')", "json_extract(r.scenario,'$.car')")


def leaderboard(db, track, layout, car):
    rows = db.all(f"SELECT a.trainee_id,u.name,MIN(l.time_ms) AS best_ms,COUNT(*) AS laps FROM laps l JOIN attempts a ON a.id=l.attempt_id "
                  f"JOIN runs r ON r.id=a.run_id JOIN users u ON u.id=a.trainee_id WHERE l.valid=1 AND {COMBO[0]}=? AND {COMBO[1]}=? "
                  f"AND {COMBO[2]}=? GROUP BY a.trainee_id ORDER BY best_ms", (track, layout, car))
    leader = rows[0]["best_ms"] if rows else None
    for rank, row in enumerate(rows, 1):
        row.update(rank=rank, gap_ms=row["best_ms"] - leader)
        lap = db.one(f"SELECT l.created FROM laps l JOIN attempts a ON a.id=l.attempt_id JOIN runs r ON r.id=a.run_id WHERE a.trainee_id=? "
                     f"AND l.valid=1 AND l.time_ms=? AND {COMBO[0]}=? AND {COMBO[1]}=? AND {COMBO[2]}=? LIMIT 1",
                     (row["trainee_id"], row["best_ms"], track, layout, car))
        row["date"] = lap["created"] if lap else None
    return rows


def combos(db):
    rows = db.all(f"SELECT {COMBO[0]} AS track,{COMBO[1]} AS layout,{COMBO[2]} AS car,json_extract(r.scenario,'$.track.name') AS track_name,"
                  f"COUNT(*) AS laps,SUM(l.valid) AS valid_laps,MIN(CASE WHEN l.valid=1 THEN l.time_ms END) AS record_ms,"
                  f"COUNT(DISTINCT a.trainee_id) AS drivers FROM laps l JOIN attempts a ON a.id=l.attempt_id JOIN runs r ON r.id=a.run_id "
                  f"GROUP BY 1,2,3 ORDER BY laps DESC")
    return [r for r in rows if r["record_ms"] is not None]


def achievements(laps, records, races):
    """Osiągnięcia jak w SimTrainer, liczone z okrążeń i wyścigów kursanta."""
    out = []
    add = lambda title, desc, done, progress="": out.append({"title": title, "desc": desc, "done": bool(done), "progress": progress})  # noqa: E731
    streak = best = 0
    for lap in laps:
        streak = streak + 1 if lap["valid"] else 0
        best = max(best, streak)
    tracks = len({(r["track"], r["layout"]) for r in records})
    add("Pierwsze okrążenie", "Ukończ pierwsze pomiarowe okrążenie", laps)
    add("Czysta dziesiątka", "10 czystych okrążeń z rzędu", best >= 10, f"{min(best, 10)}/10")
    add("Setka", "100 przejechanych okrążeń", len(laps) >= 100, f"{min(len(laps), 100)}/100")
    contested = [r for r in races if r["drivers"] >= 2]  # wyścig z co najmniej dwoma kierowcami
    add("Na podium", "Miejsce 1–3 w wyścigu", any(r["position"] <= 3 for r in contested))
    add("Zwycięzca", "Wygraj wyścig", any(r["position"] == 1 for r in contested))
    add("Rekordzista", "Najlepszy czas w grupie na dowolnej kombinacji auta i toru", any(r["rank"] == 1 for r in records))
    add("Wszechstronny", "Czyste okrążenie na 5 różnych torach", tracks >= 5, f"{min(tracks, 5)}/5")
    return out


def profile(db, trainee_id):
    laps = db.all(f"SELECT l.time_ms,l.valid,l.offtracks,l.created,a.id AS attempt_id,r.id AS run_id,{COMBO[0]} AS track,{COMBO[1]} AS layout,"
                  f"{COMBO[2]} AS car,json_extract(r.scenario,'$.track.name') AS track_name,json_extract(r.scenario,'$.track.length') AS length "
                  f"FROM laps l JOIN attempts a ON a.id=l.attempt_id JOIN runs r ON r.id=a.run_id WHERE a.trainee_id=? ORDER BY l.created",
                  (trainee_id,))
    records = {}
    for lap in laps:
        if lap["valid"]:
            key = (lap["track"], lap["layout"], lap["car"])
            if key not in records or lap["time_ms"] < records[key]["best_ms"]:
                records[key] = {"track": lap["track"], "layout": lap["layout"], "car": lap["car"], "track_name": lap["track_name"],
                                "best_ms": lap["time_ms"], "date": lap["created"]}
    for record in records.values():
        board = leaderboard(db, record["track"], record["layout"], record["car"])
        record["rank"] = next((r["rank"] for r in board if r["trainee_id"] == trainee_id), None)
        record["drivers"] = len(board)
        record["progress"] = [{"date": l["created"], "time_ms": l["time_ms"]} for l in laps
                              if l["valid"] and (l["track"], l["layout"], l["car"]) == (record["track"], record["layout"], record["car"])]
    races = []
    for run in db.all("SELECT DISTINCT r.id,r.scenario,r.created FROM runs r JOIN attempts a ON a.run_id=r.id "
                      "WHERE a.trainee_id=? AND json_extract(r.scenario,'$.race_laps') IS NOT NULL", (trainee_id,)):
        scenario = json.loads(run["scenario"])
        standing = classification(db, run["id"], scenario["race_laps"])
        mine = next((r for r in standing if r["trainee_id"] == trainee_id), None)
        if mine and mine["finished"]:
            races.append({"run_id": run["id"], "date": run["created"], "position": mine["position"], "drivers": len(standing),
                          "track_name": scenario["track"]["name"], "car": scenario["car"]})
    records = sorted(records.values(), key=lambda r: -r["date"])
    distance = sum((l["length"] or 0) for l in laps)
    return {"stats": {"laps": len(laps), "valid_laps": sum(1 for l in laps if l["valid"]),
                      "offtracks": sum(l["offtracks"] for l in laps), "distance_km": round(distance / 1000, 1),
                      "sessions": len({l["attempt_id"] for l in laps})},
            "records": records, "races": races, "achievements": achievements(laps, records, races)}


def register_coaching_routes(app, db):
    @app.post("/api/agent/attempts/{attempt_id}/laps")
    def add_lap(attempt_id: str, body: LapEvent, source=Depends(station)):
        record = require_row(db, "attempts", attempt_id)
        if record["station_id"] != source["id"]:
            raise HTTPException(403, "Próba należy do innego stanowiska")
        with db.transaction() as c:
            c.execute("INSERT OR IGNORE INTO laps VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (attempt_id, body.lap_no, body.lap, body.time_ms, int(body.valid), body.offtracks, body.reason,
                       dump(body.tips), dump(body.trace) if body.trace else None, time.time()))
        return {"ok": True}

    @app.get("/api/attempts/{attempt_id}/coach")
    def attempt_coach(attempt_id: str, current=Depends(user)):
        from .training import can_read_attempt
        can_read_attempt(db, attempt_id, current)
        rows = db.all("SELECT lap_no,lap,time_ms,valid,offtracks,reason,tips FROM laps WHERE attempt_id=? ORDER BY lap_no", (attempt_id,))
        for row in rows:
            row["tips"] = json.loads(row["tips"])
            row["valid"] = bool(row["valid"])
        return rows

    @app.get("/api/runs/{run_id}/classification")
    def run_classification(run_id: str, actor=Depends(instructor)):
        run = require_row(db, "runs", run_id)
        return classification(db, run_id, json.loads(run["scenario"]).get("race_laps"))

    @app.get("/api/combos")
    def list_combos(current=Depends(user)):
        return combos(db)

    @app.get("/api/leaderboard")
    def board(track: str = Query(max_length=100), car: str = Query(max_length=100), layout: str = Query("", max_length=100),
              current=Depends(user)):
        return leaderboard(db, track, layout, car)

    @app.get("/api/trainees/{trainee_id}/profile")
    def trainee_profile(trainee_id: str, current=Depends(user)):
        if current["role"] == "trainee" and current["id"] != trainee_id:
            raise HTTPException(403, "Brak dostępu do profilu innego kursanta")
        if not db.one("SELECT user_id FROM trainees WHERE user_id=?", (trainee_id,)):
            raise HTTPException(404, "Nie znaleziono kursanta")
        return profile(db, trainee_id)


def register_overlay_routes(app, db):
    """Wiadomości do kierowcy, układ nakładek stanowiska i podgląd nakładek w panelu."""
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from .training import enqueue

    @app.post("/api/stations/{station_id}/message")
    def message(station_id: str, body: MessageIn, actor=Depends(instructor)):
        source = require_row(db, "stations", station_id)
        if source["simulated"]:
            raise HTTPException(409, "Stanowisko demonstracyjne nie wyświetla wiadomości")
        with db.transaction() as c:
            enqueue(c, station_id, "message", {"text": body.text.strip()}, ttl=60)
            db.audit(actor["id"], "station.message", station_id, {"text": body.text}, c)
        return {"ok": True}

    @app.get("/api/stations/{station_id}/overlay")
    def get_overlay(station_id: str, actor=Depends(instructor)):
        return json.loads(require_row(db, "stations", station_id)["overlay"] or "{}")

    @app.post("/api/stations/{station_id}/overlay")
    def set_overlay(station_id: str, body: OverlayLayout, actor=Depends(instructor)):
        require_row(db, "stations", station_id)
        layout = {**body.model_dump(), "id": time.time()}
        with db.transaction() as c:
            c.execute("UPDATE stations SET overlay=? WHERE id=?", (dump(layout), station_id))
        return layout

    @app.get("/api/stations/{station_id}/overlay-state")
    def overlay_state(station_id: str, actor=Depends(instructor)):
        """Podgląd nakładek w panelu: ostatni stan przesłany przez agenta (ok. 1× na sekundę)."""
        row = require_row(db, "stations", station_id)
        state = json.loads(row["state"] or "{}")
        online = row["last_seen"] is not None and time.time() - row["last_seen"] < 12
        coach = state.get("coach") or {}
        return {**coach, "online": online, "layout": json.loads(row["overlay"] or "{}"), "station": row["name"]}

    folder = Path(__file__).resolve().parents[2] / "agent" / "racecoach_agent" / "overlay" / "static"
    if folder.is_dir():
        app.mount("/overlay-static", StaticFiles(directory=folder), name="overlay-static")

        @app.get("/overlay/{station_id}", include_in_schema=False)
        def overlay_page(station_id: str):
            return FileResponse(folder / "overlay.html")
