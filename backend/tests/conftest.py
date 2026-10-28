import time

import pytest
from fastapi.testclient import TestClient

from racecoach.app import create_app
from racecoach.security import password_hash


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, bootstrap_admin=False)
    with app.state.db.transaction() as c:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ("teacher", "teacher@local", "Instruktor", "instructor", password_hash("test-password"), time.time()))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def logged(client):
    assert client.post("/api/auth/login", json={"email": "teacher@local", "password": "test-password"}).status_code == 200
    return client
