import re
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
from racecoach_agent import csp_weather, launcher as launcher_module
from racecoach_agent.csp_weather import FORMAT, SIZE, CspWeather, WeatherChannel, set_ini_values, start_conditions
from racecoach_agent.launcher import Launcher


def test_lua_layout_matches_python_channel_format():
    lua = (csp_weather.SOURCE / "controller.lua").read_text(encoding="utf-8")
    body = re.search(r"local LAYOUT = \[\[(.*?)\]\]", lua, re.S).group(1)
    types = re.findall(r"\b(int|float)\s+(\w+)\s*;", body)
    assert "".join("i" if t == "int" else "f" for t, _ in types) == FORMAT[1:]
    assert len(types) == len(csp_weather.FIELDS) and SIZE == 48
    assert csp_weather.CHANNEL.startswith("AcTools.CSP.Limited.")  # dozwolone dla każdego typu skryptu CSP


def test_ini_edit_keeps_other_settings_and_comments():
    text = "[BASIC]\nENABLED=0 ; Active\nCONTROLLER=sol ; Controller script\nIMPLEMENTATION=sol\n\n[PERFORMANCE]\nX=1\n"
    result = set_ini_values(text, "BASIC", {"ENABLED": "1", "CONTROLLER": "racecoach"})
    assert "CONTROLLER=racecoach" in result and "ENABLED=1" in result
    assert "IMPLEMENTATION=sol" in result and "[PERFORMANCE]\nX=1" in result
    assert set_ini_values("", "BASIC", {"CONTROLLER": "racecoach"}) == "[BASIC]\nCONTROLLER=racecoach\n"


def test_channel_request_and_acknowledgement():
    buffer = bytearray(SIZE)
    channel = WeatherChannel(buffer)
    request = channel.write(.4, 1, .4, 30)
    assert channel.read()["request_id"] == request and abs(channel.read()["rain"] - .4) < 1e-6
    assert channel.wait(request, .2) is None  # gra jeszcze nie potwierdziła
    struct.pack_into("<i", buffer, 24, request)  # ackId zapisany przez kontroler
    assert channel.wait(request, .2, require_heartbeat=False)["ack_id"] == request
    assert channel.write(0, 0, 0, 0) == request + 1


def test_start_conditions_make_rainy_start_already_wet():
    assert start_conditions({"rain": .4}) == {"rain": .4, "wetness": 1.0, "water": .4}
    assert start_conditions({"rain": 0}) == {"rain": 0, "wetness": 0, "water": 0}


class FakeChannel:
    def __init__(self):
        self.writes = []

    def write(self, *values):
        self.writes.append(values)
        return len(self.writes)

    def wait(self, request, timeout, require_heartbeat=True):
        return {"ack_id": request, "applied_rain": self.writes[-1][0], "applied_wetness": self.writes[-1][1],
                "applied_water": self.writes[-1][2], "heartbeat": 5}


def make_game(tmp_path, csp=True):
    game = tmp_path / "game"
    for folder in ("content/cars/ks_mazda_mx5_cup", "content/tracks/monza/data", "content/weather/3_clear"):
        (game / folder).mkdir(parents=True)
    (game / "acs.exe").write_text("")
    if csp:
        (game / "extension/config").mkdir(parents=True)
        (game / "extension/config/weather_fx.ini").write_text("[BASIC]\nCONTROLLER=sol\n")
    return game


def scenario(rain):
    return {"track_id": "monza", "layout": "", "car": "ks_mazda_mx5_cup", "duration": 15, "mode": "individual",
            "conditions": {"air_temp": 19, "road_temp": 15, "weather": "3_clear", "time": "17:00", "grip": .8, "rain": rain}}


def windows(monkeypatch):
    import types
    monkeypatch.setattr(launcher_module, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(launcher_module, "game_running", lambda: False)


def test_rain_requires_csp_and_is_accepted_with_it(tmp_path, monkeypatch):
    windows(monkeypatch)
    without = Launcher(make_game(tmp_path / "a", csp=False), tmp_path / "a/docs", tmp_path / "a/state")
    with pytest.raises(RuntimeError, match="Custom Shaders Patch"):
        without.prepare(scenario(.4))
    with_csp = Launcher(make_game(tmp_path / "b"), tmp_path / "b/docs", tmp_path / "b/state")
    result = with_csp.prepare(scenario(.4))
    assert result["verified"] and result["weather_control"]
    assert "weather:3_clear" in with_csp.catalog()


def test_rainy_start_installs_controller_confirms_and_restores_settings(tmp_path, monkeypatch):
    windows(monkeypatch)
    game, docs = make_game(tmp_path), tmp_path / "docs"
    (docs / "cfg/extension").mkdir(parents=True)
    (docs / "cfg/extension/weather_fx.ini").write_text("[BASIC]\nCONTROLLER=sol ; mój wybór\n", encoding="utf-8")
    launcher = Launcher(game, docs, tmp_path / "state")
    channel = FakeChannel()
    launcher.weather.channel_factory = lambda: channel

    class Process:
        def poll(self): return None

    class Reader:
        def identity(self): return {"track_id": "monza", "layout": "", "car": "ks_mazda_mx5_cup"}
        def close(self): pass

    monkeypatch.setattr(launcher_module.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(launcher_module, "ACReader", Reader)
    actual = launcher.start(scenario(.4), "Kamil")
    assert actual["weather_control"] and actual["conditions_confirmation"] == "csp_controller"
    assert actual["weather_applied"] == {"rain": .4, "wetness": 1.0, "water": .4}
    assert (game / "extension/weather-controllers/racecoach/controller.lua").is_file()
    settings = (docs / "cfg/extension/weather_fx.ini").read_text(encoding="utf-8")
    assert "CONTROLLER=racecoach" in settings and "ENABLED=1" in settings
    change = launcher.weather.change(.1, .5, .05, transition=20)
    assert change["confirmed"] and channel.writes[-1] == (.1, .5, .05, 20)
    launcher.process = None
    launcher.stop()
    assert (docs / "cfg/extension/weather_fx.ini").read_text(encoding="utf-8") == "[BASIC]\nCONTROLLER=sol ; mój wybór\n"
    assert not launcher.weather.pending_restore()
