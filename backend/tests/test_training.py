import math

from racecoach.demo import seed
from racecoach.telemetry import analyze, split_laps


def setup(logged):
    seed(logged.app.state.db)
    return logged


def auth(number):
    return {"Authorization": "Bearer internal-demo-demo-0" + str(number)}


def test_group_readiness_and_verified_start(logged):
    c = setup(logged)
    payload = {"exercise_id": "group", "mode": "multiplayer", "participants": [
        {"trainee_id": "anna", "station_id": "demo-01", "plan_item_id": "anna-1"},
        {"trainee_id": "piotr", "station_id": "demo-02", "plan_item_id": "piotr-1"}]}
    created = c.post("/api/runs", json=payload)
    assert created.status_code == 201, created.text
    run = created.json()["id"]
    assert c.post(f"/api/runs/{run}/start").status_code == 409
    assert c.post("/api/runs", json=payload).status_code == 409
    for number in (1, 2):
        commands = c.get("/api/agent/commands", headers=auth(number)).json()
        command = commands[0]
        assert c.post(f"/api/agent/commands/{command['id']}/result", headers=auth(3 - number), json={"status": "succeeded", "result": {}}).status_code == 404
        response = c.post(f"/api/agent/commands/{command['id']}/result", headers=auth(number), json={"status": "succeeded", "result": {"verified": True}})
        assert response.status_code == 200
        if number == 1:
            assert c.post(f"/api/runs/{run}/start").status_code == 409
    assert c.post(f"/api/runs/{run}/start").status_code == 200
    assert c.post(f"/api/runs/{run}/start").status_code == 409
    command = c.get("/api/agent/commands", headers=auth(1)).json()[0]
    endpoint = f"/api/agent/commands/{command['id']}/result"
    assert c.post(endpoint, headers=auth(1), json={"status": "succeeded", "result": {}}).status_code == 422
    result = {"actual": {"track_id": "demo_circuit", "layout": "training", "car": "training_gt", "simulated": True}}
    assert c.post(endpoint, headers=auth(1), json={"status": "succeeded", "result": result}).status_code == 200
    assert c.post(endpoint, headers=auth(1), json={"status": "succeeded", "result": result}).status_code == 200
    assert c.post(endpoint, headers=auth(1), json={"status": "accepted", "result": {}}).status_code == 409


def test_plan_assignment_and_role_boundaries(logged):
    c = setup(logged)
    invalid = {"exercise_id": "braking", "mode": "individual", "participants": [
        {"trainee_id": "anna", "station_id": "demo-01", "plan_item_id": "piotr-0"}]}
    assert c.post("/api/runs", json=invalid).status_code == 422
    review = c.post("/api/attempts/seed-attempt-2/review", json={"note": "Zaliczone", "decision": "passed"})
    assert review.status_code == 200
    assert c.get("/api/plans").json()[0]["items"]
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"email": "anna@demo.local", "password": "Trening2026!"})
    assert all(p["trainee_id"] == "anna" for p in c.get("/api/plans").json())
    assert c.get("/api/attempts/seed-attempt-3/export").status_code == 403
    assert c.get("/api/attempts/seed-attempt-0/export").status_code == 200  # explicitly shared reference
    assert c.post("/api/attempts/seed-attempt-2/review", json={"note": "x"}).status_code == 403


def test_telemetry_retry_and_station_ownership(logged):
    c = setup(logged)
    original = c.get("/api/attempts/seed-attempt-0/export").json()["samples"][:5]
    batch = {"chunk_id": "retry", "samples": [{**p, "seq": p["seq"] + 2000, "t": p["t"] + 200} for p in original]}
    url = "/api/agent/attempts/seed-attempt-0/telemetry"
    assert c.post(url, headers=auth(2), json=batch).status_code == 403
    first = c.post(url, headers=auth(1), json=batch)
    assert first.status_code == 200, first.text
    assert first.json()["inserted"] is True
    assert c.post(url, headers=auth(1), json=batch).json()["inserted"] is False
    batch["samples"][0]["speed"] += 1
    assert c.post(url, headers=auth(1), json=batch).status_code == 409
    batch["chunk_id"] = "overlap"
    assert c.post(url, headers=auth(1), json=batch).status_code == 409


def test_timeout_preserves_station_reservation_until_confirmed_stop(logged):
    from racecoach.routes import expire_commands
    c = setup(logged)
    request = {"exercise_id": "braking", "mode": "individual", "participants": [{"trainee_id": "anna", "station_id": "demo-01", "plan_item_id": "anna-0"}]}
    run = c.post("/api/runs", json=request).json()["id"]
    db = c.app.state.db
    with db.transaction() as conn:
        conn.execute("UPDATE commands SET expires=0 WHERE json_extract(payload,'$.run_id')=?", (run,))
    expire_commands(db)
    assert db.one("SELECT status FROM runs WHERE id=?", (run,))["status"] == "attention"
    assert c.get("/api/stations").json()[0]["attempt"] is not None
    assert c.post("/api/runs", json=request).status_code == 409
    assert c.post(f"/api/runs/{run}/stop").status_code == 200
    attempt_id = db.one("SELECT id FROM attempts WHERE run_id=?", (run,))["id"]
    assert c.post(f"/api/agent/attempts/{attempt_id}/finish", headers=auth(1), json={"status": "interrupted"}).status_code == 200
    assert db.one("SELECT status FROM runs WHERE id=?", (run,))["status"] == "interrupted"


def test_late_start_ack_cannot_revive_a_cancelled_run(logged):
    c = setup(logged)
    run = c.post("/api/runs", json={"exercise_id": "braking", "mode": "individual", "participants": [{"trainee_id": "anna", "station_id": "demo-01"}]}).json()["id"]
    command = c.get("/api/agent/commands", headers=auth(1)).json()[0]
    c.post(f"/api/agent/commands/{command['id']}/result", headers=auth(1), json={"status": "succeeded", "result": {"verified": True}})
    c.post(f"/api/runs/{run}/start")
    command = c.get("/api/agent/commands", headers=auth(1)).json()[0]
    c.post(f"/api/agent/commands/{command['id']}/result", headers=auth(1), json={"status": "running", "result": {}})
    c.post(f"/api/runs/{run}/stop")
    ack = {"status": "succeeded", "result": {"actual": {"track_id": "demo_circuit", "layout": "training", "car": "training_gt", "simulated": True}}}
    assert c.post(f"/api/agent/commands/{command['id']}/result", headers=auth(1), json=ack).status_code == 409
    assert c.app.state.db.one("SELECT status FROM runs WHERE id=?", (run,))["status"] == "stopping"


def test_cross_chunk_time_reversal_is_rejected(logged):
    c = setup(logged)
    sample = c.get("/api/attempts/seed-attempt-0/export").json()["samples"][-1]
    sample.update(seq=3000, t=0)
    assert c.post("/api/agent/attempts/seed-attempt-0/telemetry", headers=auth(1), json={"chunk_id": "reversed-time", "samples": [sample]}).status_code == 409


def test_analysis_local_deltas_sum_and_reference(logged):
    c = setup(logged)
    result = c.get("/api/attempts/seed-attempt-1/analysis?reference_id=seed-attempt-0")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["delta"] > 0
    assert math.isclose(sum(s["delta"] for s in data["sections"]), data["delta"], abs_tol=1e-6)
    own = c.get("/api/attempts/seed-attempt-0/analysis").json()
    assert own["delta"] == 0
    assert all(s["delta"] == 0 for s in own["sections"])


def test_gaps_and_reversed_driving_are_not_silently_compared():
    from racecoach.demo import demo_lap
    points = demo_lap(n=100)
    assert split_laps(points)[0]["usable"] is False  # >0.5s between samples
    points = demo_lap(n=1600)
    assert split_laps(points)[0]["usable"] is True
    points[100]["progress"] = .01
    assert split_laps(points)[0]["usable"] is False
