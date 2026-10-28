"""Pogoda na żywo przez Custom Shaders Patch (CSP WeatherFX).

Agent instaluje w grze kontroler pogody „racecoach” (csp/racecoach/controller.lua), na czas sesji
wskazuje go w ustawieniach użytkownika CSP (cfg/extension/weather_fx.ini, z kopią i przywróceniem)
i przekazuje mu deszcz, mokrość oraz stojącą wodę przez pamięć współdzieloną. Kontroler potwierdza
każde polecenie i co klatkę zwiększa licznik życia, więc agent zgłasza sukces tylko po odczycie
zwrotnym z gry.
"""
from __future__ import annotations

import mmap
import os
import re
import shutil
import struct
import time
from pathlib import Path

CHANNEL = "AcTools.CSP.Limited.RaceCoachWeather"
CONTROLLER = "racecoach"
# Układ zgodny z LAYOUT w controller.lua: 12 pól po 4 bajty, little-endian.
FORMAT = "<iiffffifffii"
SIZE = struct.calcsize(FORMAT)
FIELDS = ("version", "request_id", "rain", "wetness", "water", "transition",
          "ack_id", "applied_rain", "applied_wetness", "applied_water", "heartbeat", "controller_version")
SOURCE = Path(__file__).with_name("csp") / CONTROLLER


def start_conditions(conditions):
    """Warunki startowe dla deszczowego scenariusza: tor już mokry, jak po dłuższych opadach."""
    rain = max(0.0, min(1.0, float(conditions.get("rain", 0) or 0)))
    wetness = conditions.get("wetness")
    water = conditions.get("water")
    return {"rain": rain,
            "wetness": min(1.0, rain * 4) if wetness is None else float(wetness),
            "water": rain if water is None else float(water)}


def set_ini_values(text, section, values):
    """Zmienia wartości w jednej sekcji INI, zachowując resztę pliku i komentarze."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == f"[{section.lower()}]"), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        lines.extend(f"{key}={value}" for key, value in values.items())
        return "\n".join(lines) + "\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
    missing = dict(values)
    for i in range(start + 1, end):
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*=", lines[i])
        if match and match.group(1).upper() in {k.upper() for k in missing}:
            key = next(k for k in missing if k.upper() == match.group(1).upper())
            lines[i] = f"{key}={missing.pop(key)}"
    lines[start + 1:start + 1] = [f"{key}={value}" for key, value in missing.items()]
    return "\n".join(lines) + "\n"


class WeatherChannel:
    def __init__(self, buffer=None):
        if buffer is None:
            if os.name != "nt":
                raise RuntimeError("Kanał pogody CSP wymaga Windows")
            buffer = mmap.mmap(-1, SIZE, tagname="Local\\" + CHANNEL)
        self.buffer = buffer

    def read(self):
        return dict(zip(FIELDS, struct.unpack_from(FORMAT, self.buffer, 0)))

    def write(self, rain, wetness, water, transition):
        state = self.read()
        request_id = state["request_id"] % 2_000_000_000 + 1
        struct.pack_into("<i", self.buffer, 0, 1)
        struct.pack_into("<ffff", self.buffer, 8, rain, wetness, water, transition)
        # Numer polecenia na końcu: kontroler czyta wartości dopiero po jego zmianie.
        struct.pack_into("<i", self.buffer, 4, request_id)
        return request_id

    def wait(self, request_id, timeout, require_heartbeat=True):
        first = self.read()["heartbeat"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.read()
            if state["ack_id"] == request_id and (not require_heartbeat or state["heartbeat"] != first):
                return state
            time.sleep(.1)
        return None

    def close(self):
        if hasattr(self.buffer, "close"):
            self.buffer.close()


class CspWeather:
    def __init__(self, game_dir, documents, data_dir, channel_factory=WeatherChannel):
        self.game_dir, self.documents, self.data_dir = Path(game_dir), Path(documents), Path(data_dir)
        self.channel_factory = channel_factory
        self.channel = None
        self.settings = self.documents / "cfg/extension/weather_fx.ini"
        self.backup = self.data_dir / "weather_fx.ini.backup"
        self.existed = self.data_dir / "weather_fx.ini.missing"

    def available(self):
        return (self.game_dir / "extension/config/weather_fx.ini").is_file()

    def pending_restore(self):
        return self.backup.exists() or self.existed.exists()

    def install(self):
        target = self.game_dir / "extension/weather-controllers" / CONTROLLER
        target.mkdir(parents=True, exist_ok=True)
        for source in SOURCE.iterdir():
            destination = target / source.name
            if not destination.exists() or destination.read_bytes() != source.read_bytes():
                shutil.copyfile(source, destination)

    def enable(self, conditions):
        """Przed uruchomieniem gry: kontroler, ustawienia CSP i warunki startowe."""
        self.install()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.pending_restore():
            if self.settings.exists():
                shutil.copy2(self.settings, self.backup)
            else:
                self.existed.write_text("new", encoding="utf-8")
        text = self.settings.read_text(encoding="utf-8-sig") if self.settings.exists() else ""
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(set_ini_values(text, "BASIC", {"ENABLED": "1", "CONTROLLER": CONTROLLER}), encoding="utf-8")
        if self.channel is None:
            self.channel = self.channel_factory()
        values = start_conditions(conditions)
        self.request = self.channel.write(values["rain"], values["wetness"], values["water"], 0)
        return values

    def confirm_start(self, timeout=15):
        """Po załadowaniu sesji: czy kontroler działa i przyjął warunki startowe."""
        if self.channel is None:
            return None
        return self.channel.wait(self.request, timeout)

    def change(self, rain, wetness, water, transition=30):
        if self.channel is None:
            raise RuntimeError("Kontroler pogody RaceCoach nie jest aktywny w tej sesji")
        request = self.channel.write(rain, wetness, water, transition)
        state = self.channel.wait(request, 6)
        if state is None:
            raise RuntimeError("Gra nie potwierdziła zmiany pogody; sprawdź, czy CSP WeatherFX jest włączony")
        return {"confirmed": True, "rain": rain, "wetness": wetness, "water": water, "transition_s": transition,
                "applied_now": {"rain": round(state["applied_rain"], 3), "wetness": round(state["applied_wetness"], 3),
                                "water": round(state["applied_water"], 3)},
                "source": "csp_controller"}

    def restore(self):
        if self.backup.exists():
            self.settings.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.backup, self.settings)
            self.backup.unlink()
        elif self.existed.exists():
            self.settings.unlink(missing_ok=True)
        self.existed.unlink(missing_ok=True)
