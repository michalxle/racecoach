"""Edycja i usuwanie scenariuszy, szybki przejazd, kolizje i pozycje rywali."""
import configparser

import pytest

from racecoach import server_manager as sm
from racecoach.demo import seed
from racecoach.server_manager import ServerManager

TRACK = {"id": "monza", "game_id": "monza", "name": "Monza", "layout": "", "length": 5750,
         "geometry": [[0, 0], [100, 0], [100, 100], [0, 100]],
         "sections": [{"id": "1", "name": "Sekcja 1", "start": 0, "end": 1}], "version": "v1", "source": "ai"}
CATALOG = ["track:monza:", "car:ks_mazda_mx5_cup", "car:abarth500", "weather:3_clear"]


def setup(logged, stations=1):
    seed(logged.app.state.db)
    assert logged.post("/api/tracks", json=TRACK).status_code == 201
    result = []
    for index in range(stations):
        station = logged.post("/api/stations", json={"name": f"Stanowisko {index}"}).json()
        auth = {"Authorization": "Bearer " + station["token"]}
        heartbeat = {"version": "0.1.0", "game": "idle", "capabilities": ["ac.launch", "weather.csp"], "catalog": CATALOG}
        assert logged.post("/api/agent/heartbeat", headers=auth, json=heartbeat).status_code == 200
        result.append((station, auth))
    return result


def scenario(logged, **changes):
    body = {"title": "Monza MX-5", "track_id": "monza", "car": "ks_mazda_mx5_cup", "conditions": {"weather": "3_clear"}, **changes}
    response = logged.post("/api/exercises", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"], body


def listed(logged, exercise_id):
    return next((e for e in logged.get("/api/exercises").json() if e["id"] == exercise_id), None)


def test_unused_scenario_is_edited_in_place_and_deleted(logged):
    setup(logged)
    exercise_id, body = scenario(logged)
    response = logged.put(f"/api/exercises/{exercise_id}", json={**body, "car": "abarth500", "duration": 20})
    assert response.status_code == 200 and response.json() == {"id": exercise_id, "new_revision": False}
    row = listed(logged, exercise_id)
    assert row["car"] == "abarth500" and row["duration"] == 20 and row["revision"] == 2
    assert logged.delete(f"/api/exercises/{exercise_id}").json() == {"ok": True, "archived": False}
    assert listed(logged, exercise_id) is None


def test_used_scenario_gets_new_revision_and_moves_open_plan_items(logged):
    (station, _), = setup(logged)
    exercise_id, body = scenario(logged)
    plan = logged.post("/api/plans", json={"trainee_id": "anna", "title": "Plan"}).json()["id"]
    item = logged.post(f"/api/plans/{plan}/items", json={"exercise_id": exercise_id, "title": "Monza", "goal": "Trzy okrążenia"}).json()["id"]
    run = logged.post("/api/runs", json={"exercise_id": exercise_id, "mode": "individual",
                                         "participants": [{"trainee_id": "anna", "station_id": station["id"]}]})
    assert run.status_code == 201, run.text
    assert logged.delete(f"/api/exercises/{exercise_id}").status_code == 409  # trwająca sesja
    logged.app.state.db.connection.execute("UPDATE runs SET status='completed'")
    logged.app.state.db.connection.commit()

    response = logged.put(f"/api/exercises/{exercise_id}", json={**body, "title": "Nowa nazwa"})
    assert response.json() == {"id": exercise_id, "new_revision": False}
    response = logged.put(f"/api/exercises/{exercise_id}", json={**body, "conditions": {"weather": "3_clear", "rain": .3}})
    new_id = response.json()["id"]
    assert response.json()["new_revision"] is True and new_id != exercise_id
    assert listed(logged, exercise_id)["archived"] is True
    assert listed(logged, new_id)["revision"] == 2
    items = logged.get("/api/plans").json()[0]["items"]
    assert next(i for i in items if i["id"] == item)["exercise_id"] == new_id
    assert logged.post("/api/runs", json={"exercise_id": exercise_id, "mode": "individual",
                                          "participants": [{"trainee_id": "anna", "station_id": station["id"]}]}).status_code == 409
    assert logged.delete(f"/api/exercises/{new_id}").json()["archived"] is True  # pozycja planu = historia
    assert logged.post(f"/api/exercises/{new_id}/restore").status_code == 200
    assert listed(logged, new_id)["archived"] is False


def test_quick_run_needs_no_scenario_and_stays_out_of_the_list(logged):
    (station, auth), = setup(logged)
    response = logged.post("/api/runs/quick", json={"track_id": "monza", "car": "ks_mazda_mx5_cup", "duration": 10,
                                                     "conditions": {"weather": "3_clear", "time": "15:00"}, "mode": "individual",
                                                     "participants": [{"trainee_id": "anna", "station_id": station["id"]}]})
    assert response.status_code == 201, response.text
    assert all(e["title"].startswith("Szybki") is False for e in logged.get("/api/exercises").json())
    run = next(r for r in logged.get("/api/runs").json() if r["id"] == response.json()["id"])
    assert run["title"] == "Szybki przejazd · Monza · ks_mazda_mx5_cup"
    assert run["scenario"]["quick"] is True and run["scenario"]["duration"] == 10
    command = next(c for c in logged.get("/api/agent/commands", headers=auth).json() if c["kind"] == "prepare_session")
    assert command["payload"]["scenario"]["conditions"]["time"] == "15:00"


def test_failed_quick_run_leaves_no_hidden_exercise(logged):
    (station, _), = setup(logged)
    response = logged.post("/api/runs/quick", json={"track_id": "monza", "car": "brak_auta", "mode": "individual",
                                                     "participants": [{"trainee_id": "anna", "station_id": station["id"]}]})
    assert response.status_code == 409
    assert not logged.app.state.db.one("SELECT id FROM exercises WHERE kind='quick'")


def test_heartbeat_returns_positions_of_other_drivers(logged):
    stations = setup(logged, 2)
    db = logged.app.state.db
    exercise_id, _ = scenario(logged)

    class Server:
        configured = live_weather = True
        def start(self, *a): return {"host": "192.168.1.2", "port": 9600, "http_port": 8081, "password": ""}
        def stop(self, run_id=None): pass
    logged.app.state.server_manager = Server()
    run = logged.post("/api/runs", json={"exercise_id": exercise_id, "mode": "multiplayer", "participants": [
        {"trainee_id": "anna", "station_id": stations[0][0]["id"]}, {"trainee_id": "piotr", "station_id": stations[1][0]["id"]}]})
    assert run.status_code == 201, run.text
    with db.transaction() as c:
        c.execute("UPDATE attempts SET status='running'")
    telemetry = {"seq": 1, "t": 1, "lap": 0, "progress": .4, "x": 12.5, "y": 0, "z": -3, "speed": 120, "throttle": 1,
                 "brake": 0, "steer": 0, "gear": 3, "rpm": 6000}
    beat = {"version": "0.1.0", "game": "live", "catalog": CATALOG, "telemetry": telemetry}
    logged.post("/api/agent/heartbeat", headers=stations[1][1], json=beat)
    reply = logged.post("/api/agent/heartbeat", headers=stations[0][1], json=beat).json()
    assert reply["rivals"] == [{"name": "Piotr Nowak", "x": 12.5, "z": -3, "progress": .4, "lap": 0}]


def make_server(tmp_path, monkeypatch, executable):
    folder = tmp_path / "server"
    (folder / "cfg").mkdir(parents=True)
    (folder / executable).write_bytes(b"")
    (folder / "cfg/server_cfg.ini").write_text("[SERVER]\nHTTP_PORT=8081\n")
    (folder / "cfg/csp_extra_options.ini").write_text("[EXTRA_RULES]\nNO_BACK_TO_PITS=1\n")
    monkeypatch.setenv("RACECOACH_SERVER_DIR", str(folder))
    monkeypatch.setenv("RACECOACH_SERVER_EXECUTABLE", str(folder / executable))
    monkeypatch.setenv("RACECOACH_SERVER_HOST", "192.168.1.2")
    monkeypatch.setenv("RACECOACH_PORT", "8000")

    class Process:
        def __init__(self, *args, **kwargs): self.stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    monkeypatch.setattr(sm.subprocess, "Popen", Process)
    monkeypatch.setattr(ServerManager, "_schedule_rain", lambda self, *a, **k: None)
    return folder


def group_scenario(collisions):
    return {"track_id": "monza", "layout": "", "car": "abarth500", "duration": 15, "collisions": collisions,
            "conditions": {"time": "13:30", "weather": "3_clear", "air_temp": 18, "road_temp": 20, "rain": 0, "grip": 1}}


def test_no_collisions_adds_csp_script_and_restores_file(tmp_path, monkeypatch):
    folder = make_server(tmp_path, monkeypatch, "AssettoServer.exe")
    manager = ServerManager(tmp_path / "data")
    manager.start("run", group_scenario(False), [object(), object()])
    text = (folder / "cfg/csp_extra_options.ini").read_text()
    assert "NO_BACK_TO_PITS=1" in text
    assert "SCRIPT = 'http://192.168.1.2:8000/api/ac/no-collisions.lua'" in text
    parsed = configparser.ConfigParser()
    parsed.read_string(text)
    manager.stop("run")
    assert (folder / "cfg/csp_extra_options.ini").read_text() == "[EXTRA_RULES]\nNO_BACK_TO_PITS=1\n"


def test_collisions_on_keeps_csp_options_and_kunos_refuses_ghost_mode(tmp_path, monkeypatch):
    folder = make_server(tmp_path, monkeypatch, "AssettoServer.exe")
    manager = ServerManager(tmp_path / "data")
    manager.start("run", group_scenario(True), [object()])
    assert "SCRIPT" not in (folder / "cfg/csp_extra_options.ini").read_text()
    manager.stop("run")
    kunos = make_server(tmp_path / "k", monkeypatch, "acServer.exe")
    with pytest.raises(RuntimeError, match="AssettoServer"):
        ServerManager(tmp_path / "kdata").start("run", group_scenario(False), [object()])
    assert (kunos / "cfg/server_cfg.ini").read_text() == "[SERVER]\nHTTP_PORT=8081\n"


def test_no_collisions_script_is_served(client):
    response = client.get("/api/ac/no-collisions.lua")
    assert response.status_code == 200 and "physics.disableCarCollisions" in response.text
