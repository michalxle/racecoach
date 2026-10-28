from __future__ import annotations

import dataclasses
import queue
import sys
import threading
import time
from pathlib import Path


class Hardware:
    def __init__(self, driver="off", ddcontrol=None, max_strength=25):
        self.link = None
        self.settings = {}
        self.info = None
        self.error = None
        self.revision = 0
        self.max_strength = max_strength
        self.lock = threading.RLock()
        self.reader = None
        if driver != "off":
            if not ddcontrol or not (Path(ddcontrol) / "ddcontrol/core.py").is_file():
                raise RuntimeError("Podaj --ddcontrol ze ścieżką do istniejącego wheel-control")
            sys.path.insert(0, str(Path(ddcontrol).resolve()))
            if driver == "openffboard":
                from ddcontrol.openffboard.driver import OpenFFBoardLink
                self.link = OpenFFBoardLink()
            elif driver == "ffbeast":
                from ddcontrol.ffbeast.driver import FFBeastLink
                self.link = FFBeastLink()
            else:
                raise ValueError("Nieznany sterownik sprzętu")
            from ddcontrol.gamepads import JoystickReader
            self.reader = JoystickReader()
            self.link.start()

    def drain(self):
        if not self.link:
            return
        with self.lock:
            while True:
                try:
                    event = self.link.events.get_nowait()
                except queue.Empty:
                    break
                if event.kind == "settings":
                    self.settings = event.data
                    self.revision += 1
                elif event.kind == "connected":
                    self.info = event.data
                    self.error = None
                elif event.kind == "disconnected":
                    self.info = None
                    self.settings = {}
                elif event.kind == "error":
                    self.error = str(event.data)

    def snapshot(self):
        self.drain()
        with self.lock:
            data = {"connected": bool(self.link and self.link.connected), "error": self.error, "simulated": False,
                    "max_strength": self.max_strength}
            if self.link:
                spec = self.link.spec
                field = spec.fields()[spec.strength_key]
                raw = self.settings.get(spec.strength_key)
                data.update({"firmware": spec.name, "degrees": self.settings.get(spec.range_key),
                             "strength": round((raw - field.minimum) * 100 / (field.maximum - field.minimum)) if raw is not None else None})
                live = self.link.latest_state
                if live:
                    data["live"] = dataclasses.asdict(live)
            if self.reader:
                devices = []
                for device in self.reader.enumerate():
                    sample = self.reader.read(device.id)
                    devices.append({"id": device.id, "name": device.name, "axes": sample.axes if sample else [], "buttons": sample.buttons if sample else 0})
                data["controllers"] = devices
            return data

    def apply(self, profile):
        if not self.link or not self.link.connected:
            raise RuntimeError("Baza DD nie jest podłączona")
        if not 0 <= profile["strength"] <= self.max_strength:
            raise RuntimeError(f"Profil przekracza lokalny zatwierdzony limit {self.max_strength}%")
        self.drain()
        spec = self.link.spec
        fields = spec.fields()
        field = fields[spec.strength_key]
        raw = round(field.minimum + profile["strength"] / 100 * (field.maximum - field.minimum))
        degrees_field = fields[spec.range_key]
        if degrees_field.clamp(profile["degrees"]) != profile["degrees"]:
            raise RuntimeError("Zakres obrotu nie jest obsługiwany przez tę bazę")
        before = self.revision
        self.link.set_setting(spec.range_key, profile["degrees"])
        self.link.set_setting(spec.strength_key, raw)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.drain()
            if self.revision > before:
                actual = self.snapshot()
                if actual.get("degrees") == profile["degrees"] and actual.get("strength") == profile["strength"]:
                    return {"actual": {"degrees": actual["degrees"], "strength": actual["strength"]}, "source": "device_readback"}
            time.sleep(.05)
        raise RuntimeError("Baza nie potwierdziła profilu odczytem zwrotnym; sprawdź rzeczywiste ustawienia")

    def close(self):
        if self.link:
            self.link.stop()
