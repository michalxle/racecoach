import ctypes
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
from racecoach_agent.shared_memory import ACReader, Graphics, Physics, Static, text
from racecoach_agent.storage import AgentStore
from racecoach_agent.launcher import Launcher
from racecoach_agent.track_export import export_track


def test_sdk_offsets_and_utf16_are_windows_compatible_on_any_host():
    assert Physics.speed.offset == 28
    assert Graphics.current_ms.offset == 140
    assert Graphics.progress.offset == 248
    assert Graphics.coordinates.offset == 252
    assert Static.car.offset == 68
    assert Static.layout.offset == 524
    value = Static()
    encoded = "łódź".encode("utf-16-le")
    ctypes.memmove(ctypes.addressof(value) + Static.car.offset, encoded, len(encoded))
    assert text(value.car) == "łódź"


def test_reader_ignores_repeated_packets_and_replay():
    p, g = Physics(), Graphics()
    p.packet_id, p.speed, p.gas, p.gear = 1, 100, .4, 3
    g.status, g.current_ms, g.progress = 2, 2000, .3
    class Mapping:
        def __init__(self, value): self.value = value
        def read(self): return self.value
    reader = ACReader()
    reader.maps = [Mapping(p), Mapping(g), Mapping(Static())]
    sample, status = reader.read()
    assert sample["gear"] == 2 and sample["t"] == 2
    assert reader.read() == (None, "live")
    p.packet_id = 2
    g.status = 1
    assert reader.read() == (None, "idle")
    g.status, g.laps, g.current_ms, g.last_ms = 2, 1, 100, 90000
    sample, _ = reader.read()
    assert sample["t"] == 90.1
    p.packet_id, g.laps = 3, 0
    with pytest.raises(RuntimeError): reader.read()


def test_agent_outbox_and_command_recovery_survive_restart(tmp_path):
    path = tmp_path / "agent.db"
    store = AgentStore(path)
    store.queue("/telemetry", {"chunk_id": "stable", "samples": [1, 2]})
    store.result("command-one", "running", {})
    store.close()
    store = AgentStore(path)
    store.recover_commands()
    assert store.command("command-one")["state"] == "unknown"
    first = store.pending()
    assert json.loads(first["body"])["chunk_id"] == "stable"
    assert store.pending()["id"] == first["id"]
    store.delivered(first["id"])
    assert store.pending()["route"].endswith("/result")
    store.close()


def test_launcher_generates_individual_and_group_configuration(tmp_path):
    launcher = Launcher(tmp_path, tmp_path / "docs", tmp_path / "state")
    scenario = {"track_id": "magione", "layout": "", "car": "abarth500", "duration": 15, "mode": "individual",
                "conditions": {"air_temp": 22, "road_temp": 30, "weather": "3_clear", "time": "13:30", "grip": .98}}
    config = launcher.make_config(scenario, "Anna")
    assert config["RACE"]["TRACK"] == "magione"
    assert config["LIGHTING"]["SUN_ANGLE"] == "8.0"
    assert config["REMOTE"]["ACTIVE"] == "0"
    scenario.update(mode="multiplayer", connection={"host": "192.168.1.2", "port": 9600, "http_port": 8081})
    config = launcher.make_config(scenario, "Anna")
    assert config["REMOTE"]["SERVER_IP"] == "192.168.1.2"
    assert config["REMOTE"]["ACTIVE"] == "1"


def test_track_export_reads_geometry_and_rejects_traversal(tmp_path):
    folder = tmp_path / "content/tracks/example/ai"
    folder.mkdir(parents=True)
    points = [(0., 0., 0., 0., 0), (100., 0., 0., 100., 1), (100., 0., 100., 200., 2), (0., 0., 0., 340., 3)]
    data = struct.pack("<4i", 7, len(points), 0, 0) + b"".join(struct.pack("<4fi", *p) for p in points)
    (folder / "fast_lane.ai").write_bytes(data)
    result = export_track(tmp_path, "example")
    assert result["game_id"] == "example" and result["length"] > 300
    assert result["geometry"][2] == [100, 100]
    with pytest.raises(ValueError): export_track(tmp_path, "../../outside")
