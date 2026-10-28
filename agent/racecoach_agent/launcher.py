from __future__ import annotations

import configparser
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

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
        hour = int(scenario["conditions"]["time"][:2])
        if not 8 <= hour <= 18:
            raise RuntimeError("Podstawowy adapter obsługuje godziny 08:00–18:59; pozostałe wymagają adaptera CSP")
        if scenario["conditions"].get("rain", 0):
            raise RuntimeError("Scenariusz deszczowy wymaga adaptera kontrolera CSP; nie zostanie uruchomiony jako suchy")
        if self.backup.exists() or self.existed.exists():
            raise RuntimeError("Pozostała kopia konfiguracji po poprzednim uruchomieniu. Uruchom agenta z --restore-config po zamknięciu gry")
        if scenario["mode"] == "multiplayer" and not scenario.get("connection"):
            raise RuntimeError("Brak konfiguracji serwera sesji grupowej")
        return {"verified": True, "contents": sorted(required), "simulated": False}

    def make_config(self, scenario, driver_name):
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        race_file = self.documents / "cfg/race.ini"
        if race_file.exists():
            config.read(race_file, encoding="utf-8-sig")
        for name in list(config):
            if name.startswith(("SESSION_", "CAR_", "CONDITION_")) or name in ("REPLAY", "BENCHMARK", "REMOTE", "RESTART", "GHOST_CAR"):
                config.remove_section(name)
        config["HEADER"] = {"VERSION": "2"}
        config["RACE"] = {"TRACK": scenario["track_id"], "CONFIG_TRACK": scenario["layout"], "MODEL": scenario["car"],
                          "MODEL_CONFIG": "", "SKIN": "", "CARS": "1", "AI_LEVEL": "100", "PENALTIES": "1", "DRIFT_MODE": "0"}
        config["CAR_0"] = {"MODEL": "-", "SKIN": "", "DRIVER_NAME": driver_name, "NATIONALITY": "Poland"}
        config["SESSION_0"] = {"NAME": "RaceCoach Practice", "TYPE": "1", "DURATION_MINUTES": str(scenario["duration"]), "SPAWN_SET": "PIT"}
        conditions = scenario["conditions"]
        hour, minute = map(int, conditions["time"].split(":"))
        config["LIGHTING"] = {"SUN_ANGLE": str((hour + minute / 60 - 13) * 16), "TIME_MULT": "1", "CLOUD_SPEED": "0.2"}
        config["TEMPERATURE"] = {"AMBIENT": str(conditions["air_temp"]), "ROAD": str(conditions["road_temp"])}
        config["WEATHER"] = {"NAME": conditions["weather"]}
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
        try:
            temporary = race_file.with_suffix(".racecoach.tmp")
            with temporary.open("w", encoding="utf-8") as f:
                config.write(f)
            temporary.replace(race_file)
            self.process = subprocess.Popen([str(self.game_dir / "acs.exe")], cwd=self.game_dir)
        except Exception:
            self.restore()
            raise
        reader = ACReader()
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
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
        race_file = self.documents / "cfg/race.ini"
        if self.backup.exists():
            shutil.copy2(self.backup, race_file)
            self.backup.unlink()
        elif self.existed.exists() and race_file.exists():
            race_file.unlink()
        self.existed.unlink(missing_ok=True)
