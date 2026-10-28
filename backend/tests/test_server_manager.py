import configparser

from racecoach.server_manager import ServerManager


def test_native_server_uses_relative_road_temperature_and_restores_config(tmp_path, monkeypatch):
    folder = tmp_path / "server"
    (folder / "cfg").mkdir(parents=True)
    binary = folder / "acServer.exe"
    binary.write_bytes(b"test binary is never executed")
    original = "[SERVER]\nHTTP_PORT=8081\nNAME=Original\n"
    config_file = folder / "cfg/server_cfg.ini"
    config_file.write_text(original)
    entries = folder / "cfg/entry_list.ini"
    entries.write_text("[CAR_0]\nMODEL=original\n")
    monkeypatch.setenv("RACECOACH_SERVER_DIR", str(folder))
    monkeypatch.setenv("RACECOACH_SERVER_EXECUTABLE", str(binary))
    monkeypatch.setenv("RACECOACH_SERVER_HOST", "192.168.1.2")
    class Process:
        def __init__(self, *args, **kwargs): self.stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    monkeypatch.setattr("racecoach.server_manager.subprocess.Popen", Process)
    manager = ServerManager(tmp_path / "data")
    scenario = {"track_id": "magione", "layout": "", "car": "abarth500", "duration": 15,
                "conditions": {"time": "13:30", "weather": "3_clear", "air_temp": 22, "road_temp": 29, "rain": 0, "grip": .98}}
    manager.start("test-run", scenario, [object(), object()])
    cfg = configparser.ConfigParser()
    cfg.read(config_file)
    assert float(cfg["WEATHER_0"]["BASE_TEMPERATURE_ROAD"]) == 7
    assert cfg["SERVER"]["SUN_ANGLE"] == "8"
    assert cfg["SERVER"]["MAX_CLIENTS"] == "2"
    manager.stop("test-run")
    assert config_file.read_text() == original
    assert "MODEL=original" in entries.read_text()
