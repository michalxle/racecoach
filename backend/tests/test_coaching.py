import json
import math
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
from racecoach.coaching import trace_from_points
from racecoach.routes import apply_command_result
from racecoach_agent.coach.session import LiveSession
from racecoach_agent.coach.snapshot import AcSnapshot
from racecoach_agent.content import scan
from racecoach_agent.overlay.files import AppFiles
from racecoach_agent.overlay.server import OverlayServer

N = 300
XS = [300 * math.cos(2 * math.pi * i / N) for i in range(N)]
ZS = [180 * math.sin(2 * math.pi * i / N) for i in range(N)]


def drive(session, laps, start=0, slow_corner=None):
    """Symulowana jazda po owalu z trzema hamowaniami; zwraca (ukończone okrążenia, czas ostatniego)."""
    done, last = start, 0
    for lap in range(laps):
        lap_ms = 70000 + (900 if slow_corner == lap else 0)
        for k in range(0, lap_ms, 25):
            s = k / lap_ms
            wave = abs(math.sin(3 * math.pi * s))
            slow = 30 if slow_corner == lap and 0.28 < s < 0.36 else 0
            i = int(s * N) % N
            session.process(AcSnapshot(completed_laps=done, current_ms=k, last_ms=last, spline=s, speed_kmh=150 - 70 * wave - slow,
                                       gas=0.2 if wave > .8 else 1, brake=0.8 if 0.7 < wave < 0.9 else 0, x=XS[i], z=ZS[i]))
        done, last = done + 1, lap_ms
    for _ in range(6):
        session.process(AcSnapshot(completed_laps=done, current_ms=10, last_ms=last, spline=0.0002, speed_kmh=150, x=XS[0], z=ZS[0]))
    return done, last


def test_live_session_laps_reference_tips_and_race_finish():
    session = LiveSession("a", race_laps=3, info={"trainee": "Kamil"})
    drive(session, 3, slow_corner=2)
    events = session.take_events()
    assert [e["lap_no"] for e in events] == [1, 2, 3] and [e["lap"] for e in events] == [0, 1, 2]
    assert all(e["valid"] for e in events) and events[0]["trace"]["n"] == 500
    assert "wskazówki" in events[0]["tips"]["summary"]
    assert events[2]["time_ms"] == 70900 and events[2]["tips"]["lines"]  # strata w zwolnionym zakręcie
    assert session.finished and session.summary()["best_ms"] == 70000
    state = session.overlay_state()
    assert state["race"] == {"laps": 3, "done": True} and state["ref"]["label"] == "najlepsze w sesji"
    session.set_message("Zjedź do boksu")
    assert session.overlay_state()["message"]["text"] == "Zjedź do boksu"


def test_reference_from_central_drives_delta_from_first_lap():
    first = LiveSession("a")
    drive(first, 1)
    trace = first.take_events()[0]["trace"]
    session = LiveSession("b", reference={"source": "pb", "trace": trace}, pb_ms=70000)
    session.process(AcSnapshot(completed_laps=0, current_ms=36000, spline=0.5, speed_kmh=120, x=XS[150], z=ZS[150]))
    assert session.overlay_state()["ref"]["label"] == "rekord osobisty"
    assert abs(session.live["delta_ms"] - 1000) < 50


def test_trace_from_central_points_matches_coach_format():
    points = [{"t": 10 + i * 0.07, "progress": i / 999, "speed": 100.0, "throttle": 1.0, "brake": 0.0,
               "x": XS[i * N // 1000], "z": ZS[i * N // 1000]} for i in range(1000)]
    trace = trace_from_points(points)
    assert trace["n"] == 500 and trace["t"][0] == 0 and 69000 < trace["time_ms"] < 71000
    assert all(b >= a for a, b in zip(trace["t"], trace["t"][1:])) and trace["len_m"] > 1000


def test_content_scan_reads_names_layouts_and_weather(tmp_path):
    car = tmp_path / "content/cars/ks_mazda_mx5_cup/ui"
    car.mkdir(parents=True)
    (car / "ui_car.json").write_text('{"name": "Mazda MX5 Cup",\n "description": "linia\nłamana", "brand": "Mazda", "class": "race"}', encoding="utf-8")
    (tmp_path / "content/cars/ks_mazda_mx5_cup/skins/00_red").mkdir(parents=True)
    for layout in ("club_circuit", "extended_circuit"):
        (tmp_path / f"content/tracks/ks_vallelunga/{layout}/data").mkdir(parents=True)
        (tmp_path / f"content/tracks/ks_vallelunga/ui/{layout}").mkdir(parents=True)
        (tmp_path / f"content/tracks/ks_vallelunga/ui/{layout}/ui_track.json").write_text(
            json.dumps({"name": f"Vallelunga {layout}", "length": "1746", "country": "Italy"}), encoding="utf-8")
    (tmp_path / "content/tracks/ks_vallelunga/club_circuit/ai").mkdir()
    (tmp_path / "content/tracks/ks_vallelunga/club_circuit/ai/fast_lane.ai").write_bytes(b"x")
    (tmp_path / "content/weather/3_clear").mkdir(parents=True)
    (tmp_path / "content/weather/3_clear/weather.ini").write_text("[LAUNCHER]\nNAME=Clear ; nazwa\n")
    content = scan(tmp_path)
    assert content["cars"] == [{"id": "ks_mazda_mx5_cup", "name": "Mazda MX5 Cup", "brand": "Mazda", "class": "race", "skins": 1}]
    club = next(t for t in content["tracks"] if t["layout"] == "club_circuit")
    assert club["name"] == "Vallelunga club_circuit" and club["has_ai"] and club["length_m"] == 1746
    assert not next(t for t in content["tracks"] if t["layout"] == "extended_circuit")["has_ai"]
    assert content["weather"] == [{"id": "3_clear", "name": "Clear"}] and len(content["hash"]) == 16


def test_overlay_server_and_game_app_files(tmp_path):
    session = LiveSession("a", info={"trainee": "Kamil", "goal": "Czyste okrążenia"})
    drive(session, 2)
    state = lambda: {**session.overlay_state(), "layout": {"id": 5, "pos": {}, "off": {"w-map": True}}, "map": None}  # noqa: E731
    server = OverlayServer(state, session.reference, lambda: None, port=31977)
    assert server.start()
    try:
        assert httpx.get("http://127.0.0.1:31977/state").json()["session"]["trainee"] == "Kamil"
        assert httpx.get("http://127.0.0.1:31977/reference").json()["n"] == 500
        assert "RaceCoach" in httpx.get("http://127.0.0.1:31977/kiosk").text
        assert httpx.get("http://127.0.0.1:31977/map.png").status_code == 404
    finally:
        server.stop()
    files = AppFiles(tmp_path / "game", tmp_path / "docs")
    files.update(state(), session.reference(), desktop_overlay=True)
    data = json.loads((tmp_path / "game/apps/python/RaceCoach/overlay.json").read_text(encoding="utf-8"))
    assert data["goal"] == "Czyste okrążenia" and data["desktop_overlay"] and data["layout"]["off"] == {"w-map": True}
    assert json.loads((tmp_path / "game/apps/python/RaceCoach/reference.json").read_text(encoding="utf-8"))["len_m"] > 0


def station(logged, name="Stanowisko testowe"):
    created = logged.post("/api/stations", json={"name": name}).json()
    auth = {"Authorization": "Bearer " + created["token"]}
    logged.post("/api/agent/heartbeat", headers=auth, json={"version": "0.2.0", "catalog": ["track:ks_vallelunga:club_circuit", "car:ks_mazda_mx5_cup"]})
    return created, auth


def test_track_import_from_station_content(logged):
    created, auth = station(logged)
    content = {"cars": [{"id": "ks_mazda_mx5_cup", "name": "Mazda MX5 Cup"}], "weather": [], "hash": "abc",
               "tracks": [{"id": "ks_vallelunga", "layout": "club_circuit", "name": "Vallelunga - Club", "has_ai": True}]}
    assert logged.post("/api/agent/content", headers=auth, json=content).status_code == 200
    merged = logged.get("/api/content").json()
    assert merged["cars"][0]["name"] == "Mazda MX5 Cup" and merged["tracks"][0]["track_id"] is None
    db = logged.app.state.db

    def agent():
        for _ in range(100):
            row = db.one("SELECT id FROM commands WHERE kind='export_track' AND status='queued'")
            if row:
                track = {"id": "ks_vallelunga--club_circuit", "game_id": "ks_vallelunga", "name": "Vallelunga - Club", "layout": "club_circuit",
                         "length": 1746, "geometry": [[0, 0], [10, 0], [10, 10]], "version": "v1",
                         "sections": [{"id": "1", "name": "S1", "start": 0, "end": 1}]}
                apply_command_result(db, created["id"], row["id"], "succeeded", {"track": track})
                return
            time.sleep(.05)
    worker = threading.Thread(target=agent)
    worker.start()
    response = logged.post("/api/content/tracks", json={"track": "ks_vallelunga", "layout": "club_circuit"})
    worker.join()
    assert response.json() == {"id": "ks_vallelunga--club_circuit", "imported": True}
    assert logged.post("/api/content/tracks", json={"track": "ks_vallelunga", "layout": "club_circuit"}).json()["imported"] is False
    assert logged.get("/api/agent/commands", headers=auth).json() == []
    reply = logged.post("/api/agent/heartbeat", headers=auth, json={"version": "0.2.0"}).json()
    assert reply["content_hash"] == "abc"


def test_laps_records_leaderboard_race_and_start_reference(logged):
    from racecoach.demo import seed
    seed(logged.app.state.db)
    created, auth = station(logged)
    logged.post("/api/tracks", json={"id": "ks_vallelunga--club_circuit", "game_id": "ks_vallelunga", "name": "Vallelunga - Club",
                                     "layout": "club_circuit", "length": 1746, "geometry": [[0, 0], [10, 0], [10, 10]], "version": "v1",
                                     "sections": [{"id": "1", "name": "S1", "start": 0, "end": 1}], "source": "ai"})
    exercise = logged.post("/api/exercises", json={"title": "Club", "track_id": "ks_vallelunga--club_circuit", "car": "ks_mazda_mx5_cup"}).json()["id"]
    first = LiveSession("x")
    drive(first, 1)
    trace = first.take_events()[0]["trace"]
    runs = {}
    for trainee, base in (("anna", 70000), ("piotr", 69000)):
        run = logged.post("/api/runs", json={"exercise_id": exercise, "mode": "individual", "race_laps": 2,
                                             "participants": [{"trainee_id": trainee, "station_id": created["id"]}]}).json()
        runs[trainee] = run
        attempt = run["attempts"][0]
        for n in (1, 2):
            lap = {"lap_no": n, "lap": n - 1, "time_ms": base + n * 100, "valid": True, "offtracks": 0, "tips": {"summary": "ok"},
                   "trace": trace if trainee == "anna" and n == 1 else None}
            assert logged.post(f"/api/agent/attempts/{attempt}/laps", headers=auth, json=lap).status_code == 200
        assert logged.post(f"/api/agent/attempts/{attempt}/laps", headers=auth, json=lap).status_code == 200  # ponowienie
        logged.post(f"/api/agent/attempts/{attempt}/finish", headers=auth, json={"status": "completed"})
    board = logged.get("/api/leaderboard", params={"track": "ks_vallelunga", "layout": "club_circuit", "car": "ks_mazda_mx5_cup"}).json()
    assert [(r["name"], r["best_ms"], r["gap_ms"]) for r in board][0][1:] == (69100, 0) and board[1]["gap_ms"] == 1000
    standing = logged.get(f"/api/runs/{runs['anna']['id']}/classification").json()
    assert standing[0]["finished"] and standing[0]["laps"] == 2 and standing[0]["total_ms"] == 140300
    assert logged.get(f"/api/attempts/{runs['anna']['attempts'][0]}/coach").json()[0]["tips"] == {"summary": "ok"}
    profile = logged.get("/api/trainees/anna/profile").json()
    assert profile["stats"]["laps"] == 2 and profile["records"][0]["rank"] == 2
    assert not next(a for a in profile["achievements"] if a["title"] == "Zwycięzca")["done"]  # wyścig jednoosobowy się nie liczy
    assert logged.get("/api/combos").json()[0]["record_ms"] == 69100
    # Nowa sesja Anny: wzorzec = rekord osobisty z przebiegiem, rekord czasu do nakładek.
    run = logged.post("/api/runs", json={"exercise_id": exercise, "mode": "individual",
                                         "participants": [{"trainee_id": "anna", "station_id": created["id"]}]}).json()
    command = next(c for c in logged.get("/api/agent/commands", headers=auth).json()
                   if c["kind"] == "prepare_session" and c["payload"]["run_id"] == run["id"])
    logged.post(f"/api/agent/commands/{command['id']}/result", headers=auth, json={"status": "succeeded", "result": {"verified": True}})
    assert logged.post(f"/api/runs/{run['id']}/start").status_code == 200
    start = next(c for c in logged.get("/api/agent/commands", headers=auth).json() if c["kind"] == "start_session")
    coach = start["payload"]["coach"]
    assert coach["reference"]["source"] == "pb" and coach["reference"]["trace"]["n"] == 500 and coach["pb_ms"] == 70100
    assert coach["info"]["trainee"] and coach["info"]["exercise"] == "Club"


def test_message_and_overlay_layout_reach_agent(logged):
    created, auth = station(logged)
    assert logged.post(f"/api/stations/{created['id']}/message", json={"text": "Ostatnie okrążenie"}).status_code == 200
    command = logged.get("/api/agent/commands", headers=auth).json()[0]
    assert command["kind"] == "message" and command["payload"] == {"text": "Ostatnie okrążenie"}
    layout = logged.post(f"/api/stations/{created['id']}/overlay", json={"pos": {"w-delta": {"x": .4, "y": .1}}, "off": {"w-map": True}}).json()
    reply = logged.post("/api/agent/heartbeat", headers=auth, json={"version": "0.2.0", "coach": {"active": True, "live": {"delta_ms": -120}}}).json()
    assert reply["overlay"]["id"] == layout["id"] and reply["overlay"]["off"] == {"w-map": True}
    preview = logged.get(f"/api/stations/{created['id']}/overlay-state").json()
    assert preview["online"] and preview["live"]["delta_ms"] == -120 and preview["layout"]["id"] == layout["id"]
