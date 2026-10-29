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


class FakeServerManager:
    """Zastępuje zarządzany serwer: AssettoServer z deszczem CSP albo brak serwera (wyścig wirtualny)."""

    def __init__(self, configured):
        self.configured = self.live_weather = self.rain_supported = configured
        self.started, self.changes = [], []

    def start(self, run_id, scenario, participants):
        self.started.append(scenario)
        return {"host": "192.168.1.2", "port": 9600, "http_port": 8081, "password": "", "csp_weather": True}

    def weather(self, run_id, payload):
        self.changes.append(payload)
        return {"confirmed": True, **payload, "source": "assettoserver_rcon"}

    def stop(self, run_id=None):
        pass


def group(logged, server, race_laps=None):
    seed(logged.app.state.db)
    logged.app.state.server_manager = server
    assert logged.post("/api/tracks", json=TRACK).status_code == 201
    stations = []
    for name in ("Stanowisko A", "Stanowisko B"):
        station = logged.post("/api/stations", json={"name": name}).json()
        auth = {"Authorization": "Bearer " + station["token"]}
        heartbeat = {"version": "0.1.0", "game": "idle", "capabilities": ["ac.launch", "weather.csp"],
                     "catalog": ["track:monza:", "car:ks_mazda_mx5_cup", "weather:3_clear"]}
        assert logged.post("/api/agent/heartbeat", headers=auth, json=heartbeat).status_code == 200
        stations.append((station, auth))
    exercise = logged.post("/api/exercises", json={"title": "Monza w deszczu", "track_id": "monza", "car": "ks_mazda_mx5_cup",
                                                    "conditions": {"weather": "3_clear", "rain": .6}}).json()["id"]
    body = {"exercise_id": exercise, "mode": "multiplayer",
            "participants": [{"trainee_id": t, "station_id": s["id"]} for t, (s, _) in zip(("anna", "piotr"), stations)]}
    if race_laps:
        body["race_laps"] = race_laps
    run = logged.post("/api/runs", json=body)
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    for station, auth in stations:
        command = next(c for c in logged.get("/api/agent/commands", headers=auth).json() if c["kind"] == "prepare_session")
        logged.post(f"/api/agent/commands/{command['id']}/result", headers=auth, json={"status": "succeeded", "result": {"verified": True}})
    assert logged.post(f"/api/runs/{run_id}/start").status_code == 200
    for station, auth in stations:
        command = next(c for c in logged.get("/api/agent/commands", headers=auth).json() if c["kind"] == "start_session")
        logged.post(f"/api/agent/commands/{command['id']}/result", headers=auth, json={"status": "succeeded", "result": {
            "actual": {"track_id": "monza", "layout": "", "car": "ks_mazda_mx5_cup", "simulated": False}}})
    return run_id, stations


def test_group_rain_runs_on_assettoserver_and_changes_live(logged):
    server = FakeServerManager(configured=True)
    run_id, _ = group(logged, server)
    assert server.started[0]["conditions"]["rain"] == .6
    listed = next(r for r in logged.get("/api/runs").json() if r["id"] == run_id)
    assert listed["weather_control"] is True and "connection" not in listed["scenario"]
    response = logged.post(f"/api/runs/{run_id}/weather", json={"rain": .2, "wetness": .3, "water": .1, "transition": 10})
    assert response.status_code == 200 and response.json()["source"] == "assettoserver_rcon"
    assert server.changes == [{"rain": .2, "wetness": .3, "water": .1, "transition": 10}]


def test_virtual_race_changes_weather_on_every_station(logged):
    server = FakeServerManager(configured=False)
    run_id, stations = group(logged, server, race_laps=3)
    assert server.started == []
    listed = next(r for r in logged.get("/api/runs").json() if r["id"] == run_id)
    assert listed["weather_control"] is True
    db = logged.app.state.db
    threads = [answer_weather(db, s["id"], "succeeded", {"confirmed": True, "rain": .3, "source": "csp_controller"}) for s, _ in stations]
    response = logged.post(f"/api/runs/{run_id}/weather", json={"rain": .3, "wetness": .4, "water": .1})
    for thread in threads:
        thread.join()
    assert response.status_code == 200, response.text
    assert len(response.json()["stations"]) == 2
