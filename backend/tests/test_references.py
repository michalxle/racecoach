from racecoach.demo import seed


def test_only_designated_reference_is_shared_with_trainees(logged):
    seed(logged.app.state.db)
    response = logged.post("/api/exercises/braking/reference", json={"attempt_id": "seed-attempt-2", "lap": 0})
    assert response.status_code == 200
    logged.post("/api/auth/logout")
    logged.post("/api/auth/login", json={"email": "lena@demo.local", "password": "Trening2026!"})
    records = logged.get("/api/attempts").json()
    shared = next(a for a in records if a["id"] == "seed-attempt-2")
    assert shared["trainee_name"] == "Wzorzec instruktora"
    assert shared["note"] == "" and shared["trainee_id"] == "reference"
    assert logged.get("/api/attempts/seed-attempt-2/export").status_code == 200
    assert logged.get("/api/attempts/seed-attempt-1/export").status_code == 403
    assert logged.post("/api/exercises/braking/reference", json={"attempt_id": "seed-attempt-3", "lap": 0}).status_code == 403


def test_reference_requires_matching_exercise_and_usable_lap(logged):
    seed(logged.app.state.db)
    assert logged.post("/api/exercises/group/reference", json={"attempt_id": "seed-attempt-0", "lap": 0}).status_code == 422
    assert logged.post("/api/exercises/braking/reference", json={"attempt_id": "seed-attempt-0", "lap": 99}).status_code == 422


def test_exercise_hardware_profile_requires_agent_readback(logged):
    seed(logged.app.state.db)
    payload = {"title": "Ćwiczenie z profilem", "track_id": "demo-loop", "car": "training_gt", "hardware_profile": {"degrees": 720, "strength": 20}}
    created = logged.post("/api/exercises", json=payload)
    assert created.status_code == 201, created.text
    exercise_id = created.json()["id"]
    run = logged.post("/api/runs", json={"exercise_id": exercise_id, "mode": "individual", "participants": [{"trainee_id": "anna", "station_id": "demo-01"}]}).json()
    auth = {"Authorization": "Bearer internal-demo-demo-01"}
    command = logged.get("/api/agent/commands", headers=auth).json()[0]
    url = f"/api/agent/commands/{command['id']}/result"
    assert logged.post(url, headers=auth, json={"status": "succeeded", "result": {"verified": True}}).status_code == 422
    valid = {"verified": True, "hardware": {"actual": {"degrees": 720, "strength": 20}}}
    assert logged.post(url, headers=auth, json={"status": "succeeded", "result": valid}).status_code == 200
    assert logged.post(f"/api/runs/{run['id']}/start").status_code == 200
