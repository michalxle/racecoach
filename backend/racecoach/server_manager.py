"""A dedicated AC server folder is explicitly configured by the operator.

No shell commands are accepted from the panel. Two server programs are supported:

* the original Kunos ``acServer.exe`` - dry sessions only;
* AssettoServer (``AssettoServer.exe``) - CSP WeatherFX weather, so a group session can start
  in the rain and the instructor can change rain, wetness and water while people drive.
  RaceCoach talks to it over its Source RCON port with the ``setrain`` admin command.

Runtime weather for Kunos servers still uses the separate bridge contract; an unconfigured
bridge fails explicitly instead of reporting success.
"""
from __future__ import annotations

import configparser
import logging
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

KUNOS, ASSETTOSERVER = "kunos", "assettoserver"
DEFAULT_RCON_PORT = 9610

# AssettoServer.Shared.Weather.WeatherFxType (numeric ids used in GRAPHICS=..._type=<id>).
FX_TYPES = {"LightDrizzle": 3, "Drizzle": 4, "HeavyDrizzle": 5, "LightRain": 6, "Rain": 7, "HeavyRain": 8,
            "Clear": 15, "FewClouds": 16, "ScatteredClouds": 17, "BrokenClouds": 18, "OvercastClouds": 19,
            "Fog": 20, "Mist": 21}


def fx_weather_type(weather, rain):
    """Typ pogody WeatherFX dla pakietu nieba z gry i deszczu ze scenariusza.

    Typ ustala chmury i obraz nieba; dokładną intensywność deszczu ustawia potem ``setrain``.
    """
    if rain > 0:
        if rain < .15:
            return FX_TYPES["Drizzle"]
        if rain < .45:
            return FX_TYPES["LightRain"]
        if rain < .8:
            return FX_TYPES["Rain"]
        return FX_TYPES["HeavyRain"]
    name = weather.lower()
    for keys, fx in ((("heavy_fog",), "Fog"), (("fog",), "Mist"), (("heavy_clouds", "overcast"), "OvercastClouds"),
                     (("mid_clouds", "broken"), "BrokenClouds"), (("light_clouds", "scattered"), "ScatteredClouds"),
                     (("mid_clear", "few_clouds"), "FewClouds")):
        if any(k in name for k in keys):
            return FX_TYPES[fx]
    return FX_TYPES["Clear"]


def start_rain(conditions):
    """Warunki startowe deszczu - te same co na stanowisku (agent csp_weather.start_conditions)."""
    rain = max(0.0, min(1.0, float(conditions.get("rain", 0) or 0)))
    wetness = conditions.get("wetness")
    water = conditions.get("water")
    return {"rain": rain,
            "wetness": min(1.0, rain * 4) if wetness is None else float(wetness),
            "water": rain if water is None else float(water)}


def set_yaml_keys(text, values):
    """Ustawia klucze najwyższego poziomu w extra_cfg.yml, zachowując resztę pliku i komentarze."""
    lines = text.splitlines()
    for key, value in values.items():
        pattern = re.compile(rf"^{re.escape(key)}\s*:")
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = f"{key}: {value}"
                break
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def collision_script_section(url):
    """Sekcja csp_extra_options.ini z online-skryptem CSP wyłączającym kolizje między autami."""
    return f"\n[SCRIPT_90-racecoach_no_collisions]\nSCRIPT = '{url}'\n"


class RconError(RuntimeError):
    pass


class Rcon:
    """Minimalny klient Source RCON (AssettoServer: RconPort w extra_cfg.yml, hasło = ADMIN_PASSWORD)."""
    AUTH, EXEC, AUTH_RESPONSE = 3, 2, 2

    def __init__(self, host, port, password, timeout=3.0):
        self.host, self.port, self.password, self.timeout = host, port, password, timeout

    @staticmethod
    def _packet(request_id, kind, body):
        payload = struct.pack("<ii", request_id, kind) + body.encode("ascii") + b"\x00\x00"
        return struct.pack("<i", len(payload)) + payload

    @staticmethod
    def _read_exact(sock, size):
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise RconError("Serwer zamknął połączenie RCON")
            data += chunk
        return data

    def _read(self, sock):
        (size,) = struct.unpack("<i", self._read_exact(sock, 4))
        if not 8 <= size <= 65536:
            raise RconError("Niepoprawna odpowiedź RCON")
        data = self._read_exact(sock, size)
        request_id, kind = struct.unpack("<ii", data[:8])
        return request_id, kind, data[8:].split(b"\x00", 1)[0].decode("ascii", "replace")

    def command(self, command):
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(self._packet(1, self.AUTH, self.password))
            request_id, kind, _ = self._read(sock)
            if kind != self.AUTH_RESPONSE or request_id != 1:
                raise RconError("Serwer odrzucił hasło RCON (ADMIN_PASSWORD)")
            sock.sendall(self._packet(2, self.EXEC, command))
            while True:
                request_id, _, body = self._read(sock)
                if request_id == 2:
                    return body


class ServerManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.process = None
        self.log = None
        self.run_id = None
        self.lock = threading.Lock()
        self.backups = []
        self.rcon = None
        self.rain = None
        self.rain_thread = None
        self.rain_generation = 0
        self.rain_status = None

    @property
    def configured(self):
        return bool(os.getenv("RACECOACH_SERVER_DIR") and os.getenv("RACECOACH_SERVER_EXECUTABLE") and os.getenv("RACECOACH_SERVER_HOST"))

    @property
    def kind(self):
        """Rodzaj serwera: RACECOACH_SERVER_KIND albo nazwa pliku wykonywalnego (AssettoServer.exe)."""
        explicit = (os.getenv("RACECOACH_SERVER_KIND") or "").strip().lower()
        if explicit in (KUNOS, ASSETTOSERVER):
            return explicit
        return ASSETTOSERVER if Path(os.getenv("RACECOACH_SERVER_EXECUTABLE", "")).name.lower().startswith("assettoserver") else KUNOS

    @property
    def rain_supported(self):
        return self.configured and self.kind == ASSETTOSERVER

    @property
    def live_weather(self):
        """Czy w sesji grupowej można zmieniać pogodę podczas jazdy."""
        return self.rain_supported or bool(os.getenv("RACECOACH_WEATHER_BRIDGE") and os.getenv("RACECOACH_WEATHER_TOKEN"))

    @property
    def rcon_port(self):
        return int(os.getenv("RACECOACH_SERVER_RCON_PORT", str(DEFAULT_RCON_PORT)))

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
            kind = self.kind
            cfg_path, entry_path, extra_path = folder / "cfg/server_cfg.ini", folder / "cfg/entry_list.ini", folder / "cfg/extra_cfg.yml"
            csp_path = folder / "cfg/csp_extra_options.ini"
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
            if scenario.get("race_laps"):
                config["RACE"] = {"NAME": "Wyścig", "LAPS": str(scenario["race_laps"]), "WAIT_TIME": "60", "IS_OPEN": "2"}
            else:
                config["PRACTICE"] = {"NAME": "Szkolenie", "TIME": str(scenario["duration"]), "IS_OPEN": "1"}
            conditions = scenario["conditions"]
            hour, minute = map(int, conditions["time"].split(":"))
            if not 8 * 60 <= hour * 60 + minute <= 18 * 60:
                raise RuntimeError("Bazowy serwer obsługuje godziny dzienne; pozostałe wymagają integracji CSP")
            server["SUN_ANGLE"] = str(round((hour + minute / 60 - 13) * 16))
            rain = start_rain(conditions)
            collisions = scenario.get("collisions", True)
            if not collisions and kind != ASSETTOSERVER:
                raise RuntimeError("Jazda bez kolizji wymaga AssettoServer (skrypt CSP); acServer.exe od Kunos zawsze ma kolizje. "
                                   "Włącz kolizje albo ustaw RACECOACH_SERVER_EXECUTABLE na AssettoServer.exe")
            graphics = conditions["weather"]
            if kind == ASSETTOSERVER:
                # AssettoServer czyta typ WeatherFX z GRAPHICS ("3_clear_type=7"); bez niego nie ma deszczu ani przejść.
                graphics = f"{conditions['weather']}_type={fx_weather_type(conditions['weather'], rain['rain'])}"
                server["ADMIN_PASSWORD"] = secrets.token_urlsafe(18)
            elif rain["rain"]:
                raise RuntimeError("Deszcz w sesji grupowej wymaga AssettoServer z CSP WeatherFX; acServer.exe od Kunos nie obsługuje deszczu. "
                                   "Ustaw RACECOACH_SERVER_EXECUTABLE na AssettoServer.exe (instrukcja: docs/windows-station.md)")
            config["WEATHER_0"] = {"GRAPHICS": graphics, "BASE_TEMPERATURE_AMBIENT": str(conditions["air_temp"]),
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
            managed = (cfg_path, entry_path, extra_path, csp_path) if kind == ASSETTOSERVER else (cfg_path, entry_path)
            for path in managed:
                backup = backup_dir / path.name
                if path.exists():
                    shutil.copy2(path, backup)
                    self.backups.append((path, backup))
                else:
                    self.backups.append((path, None))
            try:
                with cfg_path.open("w", encoding="utf-8") as f:
                    config.write(f, space_around_delimiters=False)
                with entry_path.open("w", encoding="utf-8") as f:
                    entries.write(f, space_around_delimiters=False)
                if kind == ASSETTOSERVER:
                    extra = extra_path.read_text(encoding="utf-8-sig") if extra_path.exists() else ""
                    extra_path.write_text(set_yaml_keys(extra, {"EnableWeatherFx": "true", "RconPort": str(self.rcon_port)}), encoding="utf-8")
                    if not collisions:
                        # Skrypt pobiera każde stanowisko z centrali (port panelu musi być otwarty w sieci: -Lan).
                        url = f"http://{os.environ['RACECOACH_SERVER_HOST']}:{os.getenv('RACECOACH_PORT', '8000')}/api/ac/no-collisions.lua"
                        current = csp_path.read_text(encoding="utf-8-sig") if csp_path.exists() else ""
                        csp_path.write_text(current.rstrip() + "\n" + collision_script_section(url), encoding="utf-8")
                self.log = (backup_dir / "server.log").open("ab")
                self.process = subprocess.Popen([str(binary)], cwd=folder, stdout=self.log, stderr=subprocess.STDOUT)
                self.run_id = run_id
            except Exception:
                self._restore()
                raise
            connection = {"host": os.environ["RACECOACH_SERVER_HOST"], "port": port,
                          "http_port": int(server.get("HTTP_PORT", "8081")), "password": server.get("PASSWORD", "")}
            self.rcon = self.rain = self.rain_status = None
            if kind == ASSETTOSERVER:
                connection["csp_weather"] = True
                self.rcon = Rcon("127.0.0.1", self.rcon_port, server["ADMIN_PASSWORD"])
                self.rain = {"rain": 0.0, "wetness": 0.0, "water": 0.0}
                # Serwer startuje kilka sekund; dokładne wartości ustawiamy w tle, gdy RCON zacznie odpowiadać.
                self._schedule_rain(rain, transition=0, wait_for_server=90)
            return connection

    def stop(self, run_id=None):
        with self.lock:
            if run_id and self.run_id != run_id:
                return
            self.rain_generation += 1
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
            self.run_id = None
            self.rcon = None
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

    # ---------- deszcz na AssettoServer ----------
    def _send_rain(self, rcon, values):
        """``setrain <intensywność> <mokrość> <woda>``; potwierdzeniem jest odpowiedź serwera."""
        numbers = [f"{max(0.0, min(1.0, values[k])):.3f}" for k in ("rain", "wetness", "water")]
        reply = rcon.command("setrain " + " ".join(numbers))
        if "rain has been set" not in reply.lower():
            # Serwer z polskimi ustawieniami regionalnymi może oczekiwać przecinka dziesiętnego.
            reply = rcon.command("setrain " + " ".join(n.replace(".", ",") for n in numbers))
        if "rain has been set" not in reply.lower():
            raise RconError("Serwer nie potwierdził zmiany deszczu: " + (reply.strip() or "brak odpowiedzi"))

    def _schedule_rain(self, target, transition, wait_for_server=0):
        """Ustawia deszcz od razu albo płynnie przez ``transition`` sekund (krok co 1 s)."""
        self.rain_generation += 1
        generation, rcon, start = self.rain_generation, self.rcon, dict(self.rain or target)
        self.rain_status = {"state": "pending", "target": target}

        def run():
            deadline = time.monotonic() + wait_for_server
            steps = max(1, int(round(transition)))
            try:
                for step in range(1, steps + 1):
                    share = step / steps
                    values = {k: start[k] + (target[k] - start[k]) * share for k in target}
                    while True:
                        if generation != self.rain_generation:
                            return
                        try:
                            self._send_rain(rcon, values)
                            break
                        except (OSError, RconError):
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(1)
                    self.rain = values
                    if step < steps:
                        time.sleep(1)
                if generation == self.rain_generation:
                    self.rain_status = {"state": "applied", "target": target}
            except Exception as exc:
                log.error("Deszcz na serwerze AC nie został ustawiony: %s", exc)
                if generation == self.rain_generation:
                    self.rain_status = {"state": "failed", "target": target, "error": str(exc)}

        if transition <= 0 and not wait_for_server:
            run()
            if self.rain_status["state"] == "failed":
                raise RconError(self.rain_status["error"])
            return
        self.rain_thread = threading.Thread(target=run, name="racecoach-server-rain", daemon=True)
        self.rain_thread.start()

    def weather(self, run_id, payload):
        if self.rcon is not None and self.run_id == run_id and self.process and self.process.poll() is None:
            target = {k: max(0.0, min(1.0, float(payload[k]))) for k in ("rain", "wetness", "water")}
            transition = float(payload.get("transition", 30) or 0)
            # Pierwszy krok wysyłamy od razu, żeby odpowiedź serwera potwierdziła, że RCON działa.
            self._send_rain(self.rcon, dict(self.rain or target) if transition > 0 else target)
            self._schedule_rain(target, transition)
            return {"confirmed": True, **target, "transition_s": transition, "source": "assettoserver_rcon"}
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
