def test_authentication_and_csrf(client):
    assert client.get("/api/trainees").status_code == 401
    assert client.post("/api/auth/login", json={"email": "teacher@local", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "teacher@local", "password": "test-password"}).status_code == 200
    assert client.post("/api/trainees", headers={"Origin": "https://attacker.invalid"}, json={}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_trainee_cannot_read_other_people_or_pair_stations(logged):
    payload = {"name": "Anna Nowak", "email": "anna@local", "password": "student-password"}
    student_id = logged.post("/api/trainees", json=payload).json()["id"]
    assert logged.post("/api/trainees", json=payload).status_code == 409
    logged.post("/api/trainees", json={**payload, "email": "other@local"})
    logged.post("/api/auth/logout")
    logged.post("/api/auth/login", json={"email": "anna@local", "password": "student-password"})
    assert [x["id"] for x in logged.get("/api/trainees").json()] == [student_id]
    assert logged.post("/api/stations", json={"name": "Stanowisko"}).status_code == 403
    assert logged.get("/api/stations").status_code == 403


def test_station_tokens_are_scoped_and_not_disclosed(logged):
    created = logged.post("/api/stations", json={"name": "Stanowisko 01"}).json()
    assert "token" in created
    stations = logged.get("/api/stations").json()
    assert "token_hash" not in stations[0]
    assert logged.get("/api/agent/commands").status_code == 401
    auth = {"Authorization": "Bearer " + created["token"]}
    assert logged.post("/api/agent/heartbeat", headers=auth, json={"version": "test"}).status_code == 200
    assert logged.get("/api/stations").json()[0]["online"] is True
