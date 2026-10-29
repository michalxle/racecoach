"""Deszcz w sesji grupowej: AssettoServer z CSP WeatherFX sterowany przez RCON."""
import configparser
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import pytest

from racecoach import server_manager as sm
from racecoach.server_manager import Rcon, ServerManager, fx_weather_type, set_yaml_keys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
from racecoach_agent.launcher import Launcher


class FakeRconServer:
    """Serwer Source RCON zgodny z AssettoServer: hasło = ADMIN_PASSWORD, odpowiedź setrain."""

    def __init__(self, password, comma_decimals=False):
        self.password, self.comma_decimals = password, comma_decimals
        self.commands = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                authed = False
                while True:
                    head = conn.recv(4)
                    if len(head) < 4:
                        break
                    (size,) = struct.unpack("<i", head)
                    data = b""
                    while len(data) < size:
                        data += conn.recv(size - len(data))
                    request_id, kind = struct.unpack("<ii", data[:8])
                    body = data[8:-2].decode("ascii")
                    if kind == 3:
                        authed = body == self.password
                        conn.sendall(self.packet(request_id if authed else -1, 2, ""))
                        if not authed:
                            break
                    elif authed and kind == 2:
                        self.commands.append(body)
                        ok = ("," in body) if self.comma_decimals else ("." in body or body.endswith(" 0"))
                        conn.sendall(self.packet(request_id, 0, "Rain has been set.\n" if ok else "Failed to parse parameter."))

    @staticmethod
    def packet(request_id, kind, body):
        payload = struct.pack("<ii", request_id, kind) + body.encode("ascii") + b"\x00"
        return struct.pack("<i", len(payload)) + payload

    def close(self):
        self.sock.close()


def make_server(tmp_path, monkeypatch, executable="AssettoServer.exe"):
    folder = tmp_path / "server"
    (folder / "cfg").mkdir(parents=True)
    binary = folder / executable
    binary.write_bytes(b"test binary is never executed")
    (folder / "cfg/server_cfg.ini").write_text("[SERVER]\nHTTP_PORT=8081\nNAME=Original\n")
    monkeypatch.setenv("RACECOACH_SERVER_DIR", str(folder))
    monkeypatch.setenv("RACECOACH_SERVER_EXECUTABLE", str(binary))
    monkeypatch.setenv("RACECOACH_SERVER_HOST", "192.168.1.2")
    monkeypatch.delenv("RACECOACH_SERVER_KIND", raising=False)

    class Process:
        def __init__(self, *args, **kwargs): self.stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout): return 0
    monkeypatch.setattr(sm.subprocess, "Popen", Process)
    return folder


def scenario(rain):
    return {"track_id": "magione", "layout": "", "car": "abarth500", "duration": 15,
            "conditions": {"time": "13:30", "weather": "3_clear", "air_temp": 18, "road_temp": 20, "rain": rain, "grip": .98}}


def test_weather_types_follow_rain_and_sky():
    assert fx_weather_type("3_clear", 0) == 15
    assert fx_weather_type("7_heavy_clouds", 0) == 19
    assert fx_weather_type("1_heavy_fog", 0) == 20
    assert fx_weather_type("3_clear", .1) == 4
    assert fx_weather_type("3_clear", .3) == 6
    assert fx_weather_type("3_clear", .6) == 7
    assert fx_weather_type("3_clear", 1) == 8


def test_yaml_keys_are_replaced_or_appended_without_touching_the_rest():
    text = "# komentarz\nEnableWeatherFx: false\nEnablePlugins:\n  - Foo\n"
    result = set_yaml_keys(text, {"EnableWeatherFx": "true", "RconPort": "9610"})
    assert "EnableWeatherFx: true" in result and "RconPort: 9610" in result
    assert "# komentarz" in result and "  - Foo" in result


def test_kunos_server_still_refuses_rain_and_keeps_files(tmp_path, monkeypatch):
    folder = make_server(tmp_path, monkeypatch, "acServer.exe")
    manager = ServerManager(tmp_path / "data")
    assert not manager.rain_supported
    with pytest.raises(RuntimeError, match="AssettoServer"):
        manager.start("run", scenario(.5), [object()])
    assert "Original" in (folder / "cfg/server_cfg.ini").read_text()
    assert not (folder / "cfg/extra_cfg.yml").exists()


def test_assettoserver_starts_rain_over_rcon_and_restores_config(tmp_path, monkeypatch):
    folder = make_server(tmp_path, monkeypatch)
    (folder / "cfg/extra_cfg.yml").write_text("EnableWeatherFx: false\nEnableAi: false\n")
    captured = {}
    real_rcon = Rcon

    def rcon_factory(host, port, password):
        captured["server"] = FakeRconServer(password)
        return real_rcon(host, captured["server"].port, password)
    monkeypatch.setattr(sm, "Rcon", rcon_factory)
    manager = ServerManager(tmp_path / "data")
    assert manager.rain_supported and manager.live_weather
    connection = manager.start("run", scenario(.6), [object(), object()])
    assert connection["csp_weather"] is True
    cfg = configparser.ConfigParser()
    cfg.read(folder / "cfg/server_cfg.ini")
    assert cfg["WEATHER_0"]["GRAPHICS"] == "3_clear_type=7"
    assert cfg["SERVER"]["ADMIN_PASSWORD"]
    extra = (folder / "cfg/extra_cfg.yml").read_text()
    assert "EnableWeatherFx: true" in extra and "RconPort: 9610" in extra and "EnableAi: false" in extra
    deadline = time.time() + 5
    while manager.rain_status["state"] == "pending" and time.time() < deadline:
        time.sleep(.05)
    assert manager.rain_status["state"] == "applied"
    assert captured["server"].commands == ["setrain 0.600 1.000 0.600"]

    result = manager.weather("run", {"rain": .2, "wetness": .4, "water": .1, "transition": 0})
    assert result["confirmed"] is True and result["source"] == "assettoserver_rcon"
    assert captured["server"].commands[-1] == "setrain 0.200 0.400 0.100"

    manager.stop("run")
    captured["server"].close()
    assert "Original" in (folder / "cfg/server_cfg.ini").read_text()
    assert (folder / "cfg/extra_cfg.yml").read_text() == "EnableWeatherFx: false\nEnableAi: false\n"


def test_rcon_retries_with_comma_decimals_for_polish_locale():
    server = FakeRconServer("secret", comma_decimals=True)
    manager = ServerManager("unused")
    manager._send_rain(Rcon("127.0.0.1", server.port, "secret"), {"rain": .5, "wetness": .5, "water": .1})
    assert server.commands == ["setrain 0.500 0.500 0.100", "setrain 0,500 0,500 0,100"]
    server.close()


def test_rcon_rejects_wrong_password():
    server = FakeRconServer("secret")
    with pytest.raises(sm.RconError, match="hasło"):
        Rcon("127.0.0.1", server.port, "wrong").command("setrain 0 0 0")
    server.close()


def test_agent_accepts_group_rain_only_from_csp_server(tmp_path, monkeypatch):
    launcher = Launcher(tmp_path, tmp_path / "docs", tmp_path / "state")
    (tmp_path / "acs.exe").write_bytes(b"")
    (tmp_path / "content/weather/3_clear").mkdir(parents=True)
    monkeypatch.setattr(launcher, "catalog", lambda: {"track:magione:", "car:abarth500"})
    monkeypatch.setattr("racecoach_agent.launcher.game_running", lambda: False)
    monkeypatch.setattr("racecoach_agent.launcher.os.name", "nt")
    group = dict(scenario(.5), mode="multiplayer", connection={"host": "192.168.1.2", "port": 9600, "http_port": 8081})
    with pytest.raises(RuntimeError, match="AssettoServer"):
        launcher.prepare(group)
    group["connection"]["csp_weather"] = True
    with pytest.raises(RuntimeError, match="Custom Shaders Patch"):
        launcher.prepare(group)
    (tmp_path / "extension/config").mkdir(parents=True)
    (tmp_path / "extension/config/weather_fx.ini").write_text("")
    assert launcher.prepare(group)["weather_control"] is False
