import json
import threading
import time

from racecoach.demo import seed
from racecoach.routes import apply_command_result

TRACK = {"id": "monza", "game_id": "monza", "name": "Monza", "layout": "", "length": 5750,
         "geometry": [[0, 0], [100, 0], [100, 100], [0, 100]],
         "sections": [{"id": "1", "name": "Sekcja 1", "start": 0, "end": 1}], "version": "v1", "source": "ai"}


def prepare(logged, capabilities, rain=.4):
    seed(logged.app.state.db)
    station = logged.post("/api/stations", json={"name": "Stanowisko testowe"}).json()
    auth = {"Authorization": "Bearer " + station["token"]}
    heartbeat = {"version": "0.1.0", "game": "idle", "capabilities": capabilities,
                 "catalog": ["track:monza:", "car:ks_mazda_mx5_cup", "weather:3_clear"]}
    assert logged.post("/api/agent/heartbeat", headers=auth, json=heartbeat).status_code == 200
    assert logged.post("/api/tracks", json=TRACK).status_code == 201
    exercise = logged.post("/api/exercises", json={"title": "Monza deszczowo", "track_id": "monza", "car": "ks_mazda_mx5_cup",
                                                    "conditions": {"weather": "3_clear", "rain": rain}}).json()["id"]
    run = logged.post("/api/runs", json={"exercise_id": exercise, "mode": "individual",
                                         "participants": [{"trainee_id": "anna", "station_id": station["id"]}]})
    return station, auth, run


def start(logged, station, auth, run_id):
    for kind, result in (("prepare_session", {"verified": True}),
                         ("start_session", {"actual": {"track_id": "monza", "layout": "", "car": "ks_mazda_mx5_cup", "simulated": False}})):
        if kind == "start_session":
            assert logged.post(f"/api/runs/{run_id}/start").status_code == 200
        command = next(c for c in logged.get("/api/agent/commands", headers=auth).json() if c["kind"] == kind)
        assert logged.post(f"/api/agent/commands/{command['id']}/result", headers=auth,
                           json={"status": "succeeded", "result": result}).status_code == 200


def answer_weather(db, station_id, status, result):
    def worker():
        for _ in range(100):
            row = db.one("SELECT id FROM commands WHERE kind='set_weather' AND status='queued'")
            if row:
                apply_command_result(db, station_id, row["id"], status, result)
                return
            time.sleep(.05)
    thread = threading.Thread(target=worker)
    thread.start()
    return thread


def test_rain_is_refused_early_without_csp_on_station(logged):
    _, _, run = prepare(logged, ["ac.launch"])
    assert run.status_code == 409 and "Custom Shaders Patch" in run.json()["detail"]


def test_live_weather_change_waits_for_station_confirmation(logged):
    station, auth, run = prepare(logged, ["ac.launch", "weather.csp"])
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    start(logged, station, auth, run_id)
    listed = next(r for r in logged.get("/api/runs").json() if r["id"] == run_id)
    assert listed["weather_control"] is True
    db = logged.app.state.db
    thread = answer_weather(db, station["id"], "succeeded", {"confirmed": True, "rain": .1, "source": "csp_controller"})
    response = logged.post(f"/api/runs/{run_id}/weather", json={"rain": .1, "wetness": .5, "water": .05, "transition": 20})
    thread.join()
    assert response.status_code == 200 and response.json()["source"] == "csp_controller"
    payload = json.loads(db.one("SELECT payload FROM commands WHERE kind='set_weather'")["payload"])
    assert payload["transition"] == 20 and payload["attempt_id"]
    assert db.one("SELECT id FROM audit WHERE action='weather.changed' AND target=?", (run_id,))
    thread = answer_weather(db, station["id"], "failed", {"error": "Gra nie potwierdziła zmiany pogody"})
    response = logged.post(f"/api/runs/{run_id}/weather", json={"rain": 0, "wetness": 0, "water": 0})
    thread.join()
    assert response.status_code == 409 and "Gra nie potwierdziła" in response.json()["detail"]
