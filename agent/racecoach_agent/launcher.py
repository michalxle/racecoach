from __future__ import annotations

import configparser
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .csp_weather import CspWeather
from .shared_memory import ACReader


def game_running():
    if os.name != "nt":
        return False
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq acs.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10)
    return '"acs.exe"' in result.stdout.lower()


class Launcher:
    def __init__(self, game_dir, documents, data_dir):
        self.game_dir = Path(game_dir).resolve()
        self.documents = Path(documents).resolve()
        self.data_dir = Path(data_dir)
        self.process = None
        self.backup = self.data_dir / "race.ini.backup"
        self.existed = self.data_dir / "race.ini.existed"
        self.cancel = None
        self.weather = CspWeather(self.game_dir, self.documents, self.data_dir)
        self.weather_active = False

    def weather_presets(self):
        folder = self.game_dir / "content/weather"
        return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []

    def catalog(self):
        result = []
        cars = self.game_dir / "content/cars"
        tracks = self.game_dir / "content/tracks"
        if cars.exists():
            result.extend("car:" + p.name for p in cars.iterdir() if p.is_dir())
        if tracks.exists():
            for track in tracks.iterdir():
                if not track.is_dir():
                    continue
                if (track / "data").exists() or (track / "data.acd").exists():
                    result.append(f"track:{track.name}:")
                for layout in track.iterdir():
                    if layout.is_dir() and ((layout / "data").exists() or (layout / "data.acd").exists()):
                        result.append(f"track:{track.name}:{layout.name}")
        result.extend("weather:" + name for name in self.weather_presets())
        return result

    def prepare(self, scenario):
        if os.name != "nt":
            raise RuntimeError("Uruchamianie Assetto Corsa wymaga Windows")
        if game_running():
            raise RuntimeError("Zamknij bieżące Assetto Corsa przed przygotowaniem sesji")
        for key in ("track_id", "layout", "car"):
            value = scenario[key]
            if (not value and key != "layout") or not re.fullmatch(r"[A-Za-z0-9_.-]*", value) or value in (".", ".."):
                raise RuntimeError("Niepoprawny identyfikator zawartości")
        required = {f"track:{scenario['track_id']}:{scenario['layout']}", "car:" + scenario["car"]}
        if not required.issubset(self.catalog()):
            raise RuntimeError("Na stanowisku brakuje wskazanego auta lub toru")
        if not (self.game_dir / "acs.exe").is_file():
            raise RuntimeError("Brak acs.exe w folderze gry")
        weather = scenario["conditions"]["weather"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", weather) or weather in (".", "..") or not (self.game_dir / "content/weather" / weather).is_dir():
            raise RuntimeError("Brak wskazanego pakietu pogody w lokalnej instalacji gry")
        hour, minute = map(int, scenario["conditions"]["time"].split(":"))
        if not 8 * 60 <= hour * 60 + minute <= 18 * 60:
            raise RuntimeError("Podstawowy adapter obsługuje godziny 08:00–18:00; pozostałe wymagają adaptera CSP")
        live_weather = scenario["mode"] != "multiplayer" and self.weather.available()
        # W sesji grupowej deszcz przychodzi z AssettoServer przez CSP; lokalnego kontrolera nie instalujemy.
        server_weather = scenario["mode"] == "multiplayer" and bool((scenario.get("connection") or {}).get("csp_weather"))
        if scenario["conditions"].get("rain", 0) and not live_weather:
            if scenario["mode"] == "multiplayer" and not server_weather:
                raise RuntimeError("Deszcz w sesji grupowej wymaga AssettoServer z CSP WeatherFX na komputerze centrali; nie zostanie uruchomiony jako suchy")
            if not self.weather.available():
                raise RuntimeError("Deszcz wymaga Custom Shaders Patch z włączonym WeatherFX (folder extension w grze); nie zostanie uruchomiony jako suchy")
        if self.backup.exists() or self.existed.exists() or self.weather.pending_restore():
            raise RuntimeError("Pozostała kopia konfiguracji po poprzednim uruchomieniu. Uruchom agenta z --restore-config po zamknięciu gry")
        if scenario["mode"] == "multiplayer" and not scenario.get("connection"):
            raise RuntimeError("Brak konfiguracji serwera sesji grupowej")
        return {"verified": True, "contents": sorted(required), "simulated": False, "weather_control": live_weather}

    def choose_skin(self, car, preferred=""):
        """Stałe malowanie: pusty SKIN w race.ini sprawia, że AC losuje malowanie przy każdym starcie."""
        folder = self.game_dir / "content/cars" / car / "skins"
        names = sorted((p.name for p in folder.iterdir() if p.is_dir()), key=str.lower) if folder.is_dir() else []
        if preferred and preferred in names:
            return preferred
        return names[0] if names else ""

    def make_config(self, scenario, driver_name):
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        race_file = self.documents / "cfg/race.ini"
        if race_file.exists():
            config.read(race_file, encoding="utf-8-sig")
        previous_skin = config.get("RACE", "SKIN", fallback="") if config.get("RACE", "MODEL", fallback="") == scenario["car"] else ""
        skin = self.choose_skin(scenario["car"], scenario.get("skin") or previous_skin)
        for name in list(config):
            if name.startswith(("SESSION_", "CAR_", "CONDITION_")) or name in ("REPLAY", "BENCHMARK", "REMOTE", "RESTART", "GHOST_CAR"):
                config.remove_section(name)
        config["HEADER"] = {"VERSION": "2"}
        config["RACE"] = {"TRACK": scenario["track_id"], "CONFIG_TRACK": scenario["layout"], "MODEL": scenario["car"],
                          "MODEL_CONFIG": "", "SKIN": skin, "CARS": "1", "AI_LEVEL": "100", "PENALTIES": "1", "DRIFT_MODE": "0"}
        config["CAR_0"] = {"MODEL": "-", "SKIN": skin, "DRIVER_NAME": driver_name, "NATIONALITY": "Poland"}
        config["SESSION_0"] = {"NAME": "RaceCoach Practice", "TYPE": "1", "DURATION_MINUTES": str(scenario["duration"]), "SPAWN_SET": "PIT"}
        conditions = scenario["conditions"]
        hour, minute = map(int, conditions["time"].split(":"))
        config["LIGHTING"] = {"SUN_ANGLE": str((hour + minute / 60 - 13) * 16), "TIME_MULT": "1", "CLOUD_SPEED": "0.2"}
        config["TEMPERATURE"] = {"AMBIENT": str(conditions["air_temp"]), "ROAD": str(conditions["road_temp"])}
        config["WEATHER"] = {"NAME": conditions["weather"]}
        config["WIND"] = {"SPEED_KMH_MIN": "0", "SPEED_KMH_MAX": "0", "DIRECTION_DEG": "0"}
        config["DYNAMIC_TRACK"] = {"SESSION_START": str(conditions["grip"] * 100), "RANDOMNESS": "0", "LAP_GAIN": "0", "SESSION_TRANSFER": "100"}
        config["REMOTE"] = {"ACTIVE": "0"}
        if scenario["mode"] == "multiplayer":
            connection = scenario["connection"]
            config["REMOTE"] = {"ACTIVE": "1", "SERVER_IP": connection["host"], "SERVER_PORT": str(connection["port"]),
                                "SERVER_HTTP_PORT": str(connection["http_port"]), "PASSWORD": connection.get("password", ""),
                                "REQUESTED_CAR": scenario["car"], "NAME": driver_name}
        return config

    def start(self, scenario, driver_name="Kursant RaceCoach"):
        self.prepare(scenario)
        config = self.make_config(scenario, driver_name)
        race_file = self.documents / "cfg/race.ini"
        race_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if race_file.exists():
            shutil.copy2(race_file, self.backup)
        else:
            self.existed.write_text("new", encoding="utf-8")
        self.weather_active = False
        try:
            if scenario["mode"] != "multiplayer" and self.weather.available():
                self.weather.enable(scenario["conditions"])
                self.weather_active = True
            temporary = race_file.with_suffix(".racecoach.tmp")
            with temporary.open("w", encoding="utf-8") as f:
                # AC czyta "KLUCZ=wartość"; spacje wokół "=" trafiają do wartości (TRACK NOT FOUND).
                config.write(f, space_around_delimiters=False)
            temporary.replace(race_file)
            self.process = subprocess.Popen([str(self.game_dir / "acs.exe")], cwd=self.game_dir)
        except Exception:
            self.restore()
            raise
        reader = ACReader()
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if self.cancel is not None and self.cancel.is_set():
                    raise RuntimeError("Uruchamianie anulowane przy wyłączeniu agenta")
                if self.process.poll() is not None:
                    raise RuntimeError("Gra zakończyła się przed potwierdzeniem sesji. Sprawdź Steam i logi AC")
                try:
                    actual = reader.identity()
                    if all(actual[k] == scenario[k] for k in ("track_id", "layout", "car")):
                        assists = self.documents / "cfg/assists.ini"
                        import hashlib
                        actual["assists_file_sha256"] = hashlib.sha256(assists.read_bytes()).hexdigest() if assists.exists() else None
                        actual["conditions_requested"] = scenario["conditions"]
                        actual["conditions_confirmation"] = "configuration_only"
                        actual["weather_control"] = False
                        if scenario["mode"] == "multiplayer" and (scenario.get("connection") or {}).get("csp_weather"):
                            actual["conditions_confirmation"] = "server_csp"
                        if self.weather_active:
                            state = self.weather.confirm_start()
                            if state is not None:
                                actual["conditions_confirmation"] = "csp_controller"
                                actual["weather_control"] = True
                                actual["weather_applied"] = {"rain": round(state["applied_rain"], 3),
                                                             "wetness": round(state["applied_wetness"], 3),
                                                             "water": round(state["applied_water"], 3)}
                            elif scenario["conditions"].get("rain", 0):
                                raise RuntimeError("Kontroler pogody RaceCoach nie uruchomił się w grze; sprawdź, czy CSP WeatherFX jest włączony")
                        return actual
                except OSError:
                    pass
                time.sleep(.5)
            raise RuntimeError("Gra nie potwierdziła żądanej sesji w ciągu 90 sekund")
        finally:
            reader.close()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.restore()

    def restore(self):
        if game_running():
            raise RuntimeError("Zamknij grę przed przywróceniem konfiguracji")
        self.weather.restore()
        self.weather_active = False
        race_file = self.documents / "cfg/race.ini"
        if self.backup.exists():
            shutil.copy2(self.backup, race_file)
            self.backup.unlink()
        elif self.existed.exists() and race_file.exists():
            race_file.unlink()
        self.existed.unlink(missing_ok=True)
