import sqlite3

import pytest
from fastapi.testclient import TestClient

from racecoach.app import create_app


def test_demo_data_cannot_be_opened_as_real_installation(tmp_path):
    app = create_app(tmp_path, demo=True)
    with TestClient(app) as client:
        assert client.get('/api/meta').json()['demo'] is True
    with pytest.raises(RuntimeError, match='folder danych'):
        create_app(tmp_path, demo=False)


def test_new_real_installation_has_no_demo_accounts(tmp_path):
    app = create_app(tmp_path, demo=False)
    with TestClient(app) as client:
        assert client.get('/api/meta').json()['demo_login'] is None
        assert client.post('/api/auth/login',json={'email':'instruktor@demo.local','password':'Trening2026!'}).status_code == 401
        assert app.state.db.one('SELECT count(*) AS n FROM stations')['n'] == 0
        assert (tmp_path / 'bootstrap.json').is_file()


def test_second_server_cannot_reset_the_same_demo_database(tmp_path):
    from racecoach.instance_lock import InstanceLock
    first = InstanceLock(tmp_path / 'server.lock')
    second = InstanceLock(tmp_path / 'server.lock')
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match='Inna centrala'):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_sqlite_backup_captures_wal_and_refuses_overwrite(tmp_path, monkeypatch):
    from racecoach.backup import main
    folder = tmp_path / 'source'
    folder.mkdir()
    db = sqlite3.connect(folder / 'racecoach.sqlite3')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE sample(value TEXT)')
    db.execute("INSERT INTO sample VALUES ('zapisane')")
    db.commit()
    destination = tmp_path / 'backup.sqlite3'
    monkeypatch.setattr('sys.argv', ['backup','--data',str(folder),'--output',str(destination)])
    main()
    with sqlite3.connect(destination) as restored:
        assert restored.execute('SELECT value FROM sample').fetchone()[0] == 'zapisane'
    with pytest.raises(FileExistsError):
        main()
    db.close()
