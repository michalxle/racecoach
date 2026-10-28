"""Explicitly synthetic data. The demo does not claim a connection to a simulator."""
from __future__ import annotations

import asyncio
import json
import math
import time

from .db import dump
from .routes import apply_command_result
from .security import digest, password_hash
from .telemetry import store_chunk
from .training import finish_attempt


def coordinate(p):
    angle = p * 2 * math.pi
    return [math.cos(angle) * (390 + 100 * math.sin(3 * angle)),
            math.sin(angle) * (250 + 65 * math.cos(2 * angle))]


def demo_lap(factor=1.0, variant=0, lap=0, seq_start=0, start_time=0, n=1600):
    points = []
    elapsed = start_time
    previous_speed = 140
    for i in range(n + 1):
        p = i / n
        corners = [(0.14, .035), (.34, .025), (.52, .04), (.72, .03), (.88, .022)]
        slow = sum(math.exp(-((p - center) / width) ** 2) for center, width in corners)
        speed = max(50, (168 - 100 * slow) / factor + variant * 2 * math.sin(p * 18))
        if i:
            elapsed += (3200 / n) / ((speed + previous_speed) / 2 / 3.6)
        previous_speed = speed
        braking = max(math.exp(-((p - (center - .025 + variant * .001)) / (width * .48)) ** 2) for center, width in corners)
        throttle = max(.05, min(1, 1 - braking * .95 - slow * .3))
        x, z = coordinate(p)
        points.append({"seq": seq_start + i, "t": elapsed, "lap": lap, "progress": p,
                       "x": x + variant * 1.5 * math.sin(p * 24), "y": 0., "z": z + variant * math.cos(p * 30),
                       "speed": speed, "throttle": throttle, "brake": braking,
                       "steer": math.sin(p * 2 * math.pi) * .2 + slow * .25,
                       "gear": max(2, min(6, int(speed / 32))), "rpm": 4000 + speed * 18, "valid": True})
    return points


def station_state():
    return {"version": "demo-1", "game": "idle", "hardware": {"connected": True, "firmware": "OpenFFBoard · demo", "degrees": 900, "strength": 15, "simulated": True},
            "capabilities": ["hardware.profile", "ac.launch", "ac.multiplayer", "weather.demo"], "catalog": [],
            "active_attempt": None, "telemetry": None, "error": None}


def seed(db):
    if db.one("SELECT id FROM tracks WHERE id='demo-loop'"):
        teacher = db.one("SELECT id FROM users WHERE role='instructor' LIMIT 1")
        if teacher and db.one("SELECT id FROM attempts WHERE id='seed-attempt-0'"):
            with db.transaction() as c:
                c.execute("INSERT OR IGNORE INTO exercise_references VALUES (?,?,?,?,?)", ("braking", "seed-attempt-0", 0, teacher["id"], time.time()))
        return
    now = time.time()
    sections = [{"id": str(i + 1), "name": name, "start": start, "end": end} for i, (name, start, end) in enumerate([
        ("Prosta startowa", 0, .1), ("Zakręt 1 · hamowanie", .1, .23), ("Szykana", .23, .43),
        ("Łuk techniczny", .43, .63), ("Nawrót", .63, .8), ("Ostatni zakręt", .8, 1)])]
    geometry = [coordinate(i / 359) for i in range(360)]
    with db.transaction() as c:
        c.execute("INSERT INTO tracks(id,name,layout,length,geometry,sections,version,source,game_id) VALUES (?,?,?,?,?,?,?,?,?)",
                  ("demo-loop", "Circuit École", "training", 3200, dump(geometry), dump(sections), "demo-v1", "demo", "demo_circuit"))
        for key, name, email in [("anna", "Anna Kowalska", "anna@demo.local"), ("piotr", "Piotr Nowak", "piotr@demo.local"), ("lena", "Lena Wiśniewska", "lena@demo.local")]:
            c.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (key, email, name, "trainee", password_hash("Trening2026!"), now))
            c.execute("INSERT INTO trainees VALUES (?,?)", (key, "Konto demonstracyjne. Wszystkie przejazdy są syntetyczne."))
        for key, title, mode, rain in [("braking", "Hamowanie i płynne wyjście", "either", 0), ("group", "Jazda za instruktorem", "multiplayer", 0), ("wet", "Adaptacja do mokrej nawierzchni", "either", .5)]:
            conditions = {"weather": "3_clear", "air_temp": 22, "road_temp": 29, "grip": 1, "rain": rain, "time": "13:00"}
            c.execute("INSERT INTO exercises(id,title,track_id,car,conditions,duration,mode,revision) VALUES (?,?,?,?,?,?,?,?)", (key, title, "demo-loop", "training_gt", dump(conditions), 15, mode, 1))
        for key, name in [("demo-01", "Stanowisko 01"), ("demo-02", "Stanowisko 02")]:
            c.execute("INSERT INTO stations VALUES (?,?,?,?,?,?,?)", (key, name, digest("internal-demo-" + key), 1, now, now, dump(station_state())))
        for student in ("anna", "piotr", "lena"):
            c.execute("INSERT INTO plans VALUES (?,?,?,?)", ("plan-" + student, student, "Fundamenty techniki jazdy", now))
            for i, (exercise, title, goal) in enumerate([("braking", "Kontrola hamowania", "Powtarzalny punkt hamowania i płynne zwalnianie pedału."),
                                                       ("group", "Linia i praca w grupie", "Utrzymanie linii za instruktorem i świadome wyjście z zakrętu."),
                                                       ("wet", "Zmienne warunki", "Dostosowanie prędkości wejścia do przyczepności.")]):
                c.execute("INSERT INTO plan_items(id,plan_id,exercise_id,title,goal,criteria,mode,sequence,status) VALUES (?,?,?,?,?,?,?,?,?)",
                          (f"{student}-{i}", "plan-" + student, exercise, title, goal, dump("Trzy powtarzalne okrążenia oraz ocena instruktora."), "multiplayer" if exercise == "group" else "either", i + 1, "passed" if i == 0 and student == "piotr" else "ready"))
        track = {"id": "demo-loop", "game_id": "demo_circuit", "name": "Circuit École", "layout": "training", "length": 3200, "geometry": geometry,
                 "sections": sections, "version": "demo-v1", "source": "demo"}
        scenario = {"exercise_id": "braking", "revision": 1, "track_key": "demo-loop", "track_id": "demo_circuit", "layout": "training", "track": track,
                    "car": "training_gt", "conditions": {"weather": "3_clear", "air_temp": 22, "road_temp": 29, "grip": 1, "rain": 0, "time": "13:00"}, "duration": 15, "mode": "individual"}
        for i, (student, factor, note) in enumerate([("piotr", 1, "Przejazd referencyjny · syntetyczny"), ("anna", 1.04, "Późne zwolnienie hamulca w nawrocie; popracuj nad wyjściem."), ("anna", 1.025, "Lepsza powtarzalność punktów hamowania."), ("lena", 1.06, "Pierwsza sesja diagnostyczna.")]):
            run_id, attempt_id = f"seed-run-{i}", f"seed-attempt-{i}"
            created = now - (4 - i) * 3600
            c.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (run_id, "individual", "braking", dump(scenario), "completed", created, created + 240))
            c.execute("INSERT INTO attempts(id,run_id,trainee_id,station_id,plan_item_id,status,config,note,created) VALUES (?,?,?,?,?,?,?,?,?)",
                      (attempt_id, run_id, student, "demo-01", student + "-0", "completed", dump({"track_id": "demo_circuit", "layout": "training", "car": "training_gt", "simulated": True}), note, created))
    for i, factor in enumerate([1, 1.04, 1.025, 1.06]):
        samples = demo_lap(factor, i * .4)
        for index in range(0, len(samples), 500):
            store_chunk(db, f"seed-attempt-{i}", f"seed-{index}", samples[index:index + 500])
    instructor = db.one("SELECT id FROM users WHERE role='instructor' LIMIT 1")
    if instructor:
        with db.transaction() as c:
            c.execute("INSERT INTO exercise_references VALUES (?,?,?,?,?)", ("braking", "seed-attempt-0", 0, instructor["id"], time.time()))


async def demo_loop(db):
    jobs = {}
    # A restart never resumes a process or an unconfirmed demo start silently.
    with db.transaction() as c:
        c.execute("UPDATE attempts SET status='interrupted',note='Demo uruchomione ponownie' WHERE station_id IN (SELECT id FROM stations WHERE simulated=1) AND status IN ('running','preparing','ready','stopping','attention')")
        c.execute("UPDATE commands SET status='unknown',result=? WHERE station_id IN (SELECT id FROM stations WHERE simulated=1) AND status IN ('queued','accepted','running')", (dump({"error": "Restart demonstracji"}),))
        c.execute("UPDATE runs SET status='interrupted',ended=? WHERE status NOT IN ('completed','interrupted') AND NOT EXISTS (SELECT 1 FROM attempts a JOIN stations s ON s.id=a.station_id WHERE a.run_id=runs.id AND s.simulated=0)", (time.time(),))
        c.execute("UPDATE stations SET state=? WHERE simulated=1", (dump(station_state()),))
    while True:
        for source in db.all("SELECT * FROM stations WHERE simulated=1"):
            state = json.loads(source["state"])
            commands = db.all("SELECT * FROM commands WHERE station_id=? AND status='queued' ORDER BY created", (source["id"],))
            for cmd in commands:
                payload = json.loads(cmd["payload"])
                if cmd["expires"] < time.time():
                    continue
                if cmd["kind"] == "prepare_session":
                    profile = payload["scenario"].get("hardware_profile")
                    if profile:
                        state["hardware"].update(profile)
                    result = {"verified": True, "simulated": True}
                    if profile:
                        result["hardware"] = {"actual": profile, "simulated": True}
                    apply_command_result(db, source["id"], cmd["id"], "succeeded", result)
                    state["game"] = "idle"
                elif cmd["kind"] == "start_session":
                    scenario = payload["scenario"]
                    actual = {k: scenario[k] for k in ("track_id", "layout", "car")}
                    actual["simulated"] = True
                    actual["hardware"] = dict(state["hardware"])
                    apply_command_result(db, source["id"], cmd["id"], "succeeded", {"actual": actual})
                    first = demo_lap(1.02 if source["id"] == "demo-01" else 1.045, .5)
                    second = demo_lap(1.015, .3, lap=1, seq_start=len(first), start_time=first[-1]["t"] + .01)
                    jobs[source["id"]] = {"samples": first + second, "index": 0, "attempt_id": payload["attempt_id"], "config": actual}
                    state.update({"game": "live", "active_attempt": payload["attempt_id"]})
                elif cmd["kind"] == "stop_session":
                    jobs.pop(source["id"], None)
                    record = db.one("SELECT config FROM attempts WHERE id=?", (payload["attempt_id"],))
                    finish_attempt(db, payload["attempt_id"], "interrupted", json.loads(record["config"]), "Zatrzymano demo przez instruktora")
                    apply_command_result(db, source["id"], cmd["id"], "succeeded", {"stopped": True, "simulated": True})
                    state.update({"game": "idle", "active_attempt": None})
                elif cmd["kind"] == "hardware_profile":
                    state["hardware"].update(payload)
                    apply_command_result(db, source["id"], cmd["id"], "succeeded", {"actual": payload, "simulated": True})
            job = jobs.get(source["id"])
            if job:
                chunk = job["samples"][job["index"]:job["index"] + 35]
                if chunk:
                    store_chunk(db, job["attempt_id"], "demo-" + str(job["index"]), chunk)
                    job["index"] += len(chunk)
                    state["telemetry"] = chunk[-1]
                else:
                    finish_attempt(db, job["attempt_id"], "completed", job["config"], "Przyspieszona sesja demonstracyjna · dane syntetyczne")
                    jobs.pop(source["id"], None)
                    state.update({"game": "idle", "active_attempt": None})
            with db.transaction() as c:
                c.execute("UPDATE stations SET last_seen=?,state=? WHERE id=?", (time.time(), dump(state), source["id"]))
        await asyncio.sleep(.25)
