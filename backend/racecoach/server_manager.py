"""A dedicated AC server folder is explicitly configured by the operator.

No shell commands are accepted from the panel. Runtime weather is a separate bridge
contract; an unconfigured bridge fails explicitly instead of reporting success.
"""
from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import threading
from pathlib import Path

import httpx


class ServerManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.process = None
        self.log = None
        self.run_id = None
        self.lock = threading.Lock()
        self.backups = []

    @property
    def configured(self):
        return bool(os.getenv("RACECOACH_SERVER_DIR") and os.getenv("RACECOACH_SERVER_EXECUTABLE") and os.getenv("RACECOACH_SERVER_HOST"))

    def start(self, run_id, scenario, participants):
        with self.lock:
            if not self.configured:
                raise RuntimeError("Skonfiguruj folder, plik wykonywalny i adres serwera AC w środowisku centrali")
            if self.process and self.process.poll() is None:
                raise RuntimeError("Zarządzany serwer AC jest już zajęty")
            folder = Path(os.environ["RACECOACH_SERVER_DIR"]).resolve()
            binary = Path(os.environ["RACECOACH_SERVER_EXECUTABLE"]).resolve()
            if not binary.is_file() or not (folder / "cfg").is_dir():
                raise RuntimeError("Niepoprawna instalacja dedykowanego serwera AC")
            cfg_path, entry_path = folder / "cfg/server_cfg.ini", folder / "cfg/entry_list.ini"
            if not cfg_path.exists():
                raise RuntimeError("Brak bazowego cfg/server_cfg.ini; przygotuj oddzielną instalację serwera")
            config = configparser.ConfigParser(interpolation=None)
            config.optionxform = str
            config.read(cfg_path, encoding="utf-8-sig")
            if "SERVER" not in config:
                raise RuntimeError("Brak sekcji SERVER w konfiguracji")
            port = int(os.getenv("RACECOACH_SERVER_PORT", "9600"))
            server = config["SERVER"]
            server.update({"NAME": "RaceCoach Training", "TRACK": scenario["track_id"], "CONFIG_TRACK": scenario["layout"],
                           "CARS": scenario["car"], "MAX_CLIENTS": str(len(participants)), "PICKUP_MODE_ENABLED": "1",
                           "REGISTER_TO_LOBBY": "0", "UDP_PORT": str(port), "TCP_PORT": str(port)})
            for name in list(config.sections()):
                if name in ("PRACTICE", "QUALIFY", "RACE", "BOOK", "DYNAMIC_TRACK") or name.startswith("WEATHER_"):
                    config.remove_section(name)
            config["PRACTICE"] = {"NAME": "Szkolenie", "TIME": str(scenario["duration"]), "IS_OPEN": "1"}
            conditions = scenario["conditions"]
            hour, minute = map(int, conditions["time"].split(":"))
            if not 8 * 60 <= hour * 60 + minute <= 18 * 60:
                raise RuntimeError("Bazowy serwer obsługuje godziny dzienne; pozostałe wymagają integracji CSP")
            server["SUN_ANGLE"] = str(round((hour + minute / 60 - 13) * 16))
            if conditions["rain"]:
                raise RuntimeError("Deszcz wymaga skonfigurowanej integracji CSP; bazowy serwer nie potwierdza tego scenariusza")
            config["WEATHER_0"] = {"GRAPHICS": conditions["weather"], "BASE_TEMPERATURE_AMBIENT": str(conditions["air_temp"]),
                                   "BASE_TEMPERATURE_ROAD": str(conditions["road_temp"] - conditions["air_temp"]), "VARIATION_AMBIENT": "0", "VARIATION_ROAD": "0",
                                   "WIND_BASE_SPEED_MIN": "0", "WIND_BASE_SPEED_MAX": "0", "WIND_BASE_DIRECTION": "0", "WIND_VARIATION_DIRECTION": "0"}
            config["DYNAMIC_TRACK"] = {"SESSION_START": str(conditions["grip"] * 100), "RANDOMNESS": "0", "LAP_GAIN": "0", "SESSION_TRANSFER": "100"}
            entries = configparser.ConfigParser(interpolation=None)
            entries.optionxform = str
            for index, _ in enumerate(participants):
                entries[f"CAR_{index}"] = {"MODEL": scenario["car"], "SKIN": "", "SPECTATOR_MODE": "0", "DRIVERNAME": "", "TEAM": "", "GUID": "", "BALLAST": "0"}
            # Backups belong to this manager, not to a server managed by another program.
            self.backups = []
            backup_dir = self.data_dir / "server-backups" / run_id
            backup_dir.mkdir(parents=True, exist_ok=True)
            for path in (cfg_path, entry_path):
                backup = backup_dir / path.name
                if path.exists():
                    shutil.copy2(path, backup)
                    self.backups.append((path, backup))
                else:
                    self.backups.append((path, None))
            try:
                with cfg_path.open("w", encoding="utf-8") as f:
                    config.write(f)
                with entry_path.open("w", encoding="utf-8") as f:
                    entries.write(f)
                self.log = (backup_dir / "server.log").open("ab")
                self.process = subprocess.Popen([str(binary)], cwd=folder, stdout=self.log, stderr=subprocess.STDOUT)
                self.run_id = run_id
            except Exception:
                self._restore()
                raise
            return {"host": os.environ["RACECOACH_SERVER_HOST"], "port": port,
                    "http_port": int(server.get("HTTP_PORT", "8081")), "password": server.get("PASSWORD", "")}

    def stop(self, run_id=None):
        with self.lock:
            if run_id and self.run_id != run_id:
                return
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
            self.run_id = None
            self._restore()

    def _restore(self):
        if self.log:
            self.log.close()
            self.log = None
        for path, backup in self.backups:
            if backup:
                shutil.copy2(backup, path)
            elif path.exists():
                path.unlink()
        self.backups = []

    def weather(self, run_id, payload):
        bridge = os.getenv("RACECOACH_WEATHER_BRIDGE")
        secret = os.getenv("RACECOACH_WEATHER_TOKEN")
        if not bridge or not secret:
            raise RuntimeError("Brak mostu pogodowego CSP. Zmiana podczas jazdy jest niedostępna")
        response = httpx.post(bridge.rstrip("/") + "/weather", json={"run_id": run_id, **payload},
                              headers={"Authorization": "Bearer " + secret}, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get("confirmed") is not True:
            raise RuntimeError("Most pogodowy nie potwierdził wykonania")
        return result
