from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from .shared_memory import ACReader
from .launcher import game_running

log = logging.getLogger("racecoach.agent")


def monotonic_samples(samples):
    """Usuwa próbki z cofniętym czasem lub numerem (np. zapisane przez starszą wersję na linii mety)."""
    result = []
    for sample in samples:
        if not isinstance(sample, dict) or "t" not in sample or "seq" not in sample:
            return samples
        if result and (sample["seq"] <= result[-1]["seq"] or sample["t"] < result[-1]["t"]):
            log.warning("Pomijam próbkę %s z cofniętym czasem %.3f s", sample["seq"], sample["t"])
            continue
        result.append(sample)
    return result


class Agent:
    def __init__(self, server, token, store, launcher, hardware):
        self.client = httpx.Client(base_url=server.rstrip("/"), headers={"Authorization": "Bearer " + token}, timeout=4)
        self.store, self.launcher, self.hardware = store, launcher, hardware
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.recorder = None
        self.record_stop = threading.Event()
        self.lock = threading.RLock()
        self.active = None
        self.latest = None
        self.game = "idle"
        self.error = None
        self.shutdown = threading.Event()
        self.launcher.cancel = self.shutdown

    def flush(self):
        for _ in range(12):
            row = self.store.pending()
            if not row:
                return
            body = json.loads(row["body"])
            telemetry = row["route"].endswith("/telemetry")
            if telemetry:
                body["samples"] = monotonic_samples(body.get("samples", []))
                if not body["samples"]:
                    self.store.delivered(row["id"])
                    continue
            response = self.client.post(row["route"], json=body)
            if response.status_code in (404, 409) and "/commands/" in row["route"]:
                log.warning("Wynik polecenia wymaga uzgodnienia: %s", response.text)
                self.store.delivered(row["id"])
                continue
            if response.status_code == 422 and telemetry:
                # Ponawianie odrzuconej porcji zablokowałoby kolejkę, także zakończenie próby.
                log.error("Centrala odrzuciła porcję telemetrii %s; pomijam ją: %s", body.get("chunk_id"), response.text[:500])
                self.store.delivered(row["id"])
                continue
            response.raise_for_status()
            self.store.delivered(row["id"])

    def execute(self, command):
        command_id, payload, kind = command["id"], command["payload"], command["kind"]
        if command["expires"] <= time.time():
            return
        self.store.result(command_id, "running", {})  # durable before any side effect
        try:
            if kind == "prepare_session":
                if self.active:
                    raise RuntimeError("Stanowisko prowadzi już inną próbę")
                result = self.launcher.prepare(payload["scenario"])
                if payload["scenario"].get("hardware_profile"):
                    result["hardware"] = self.hardware.apply(payload["scenario"]["hardware_profile"])
            elif kind == "start_session":
                if self.active:
                    raise RuntimeError("Stanowisko prowadzi już inną próbę")
                self.game = "starting"
                profile = payload["scenario"].get("hardware_profile")
                if profile:
                    hardware = self.hardware.snapshot()
                    if any(hardware.get(k) != profile[k] for k in ("degrees", "strength")):
                        raise RuntimeError("Profil sprzętu zmienił się po przygotowaniu sesji")
                actual = self.launcher.start(payload["scenario"])
                actual["hardware"] = self.hardware.snapshot()
                with self.lock:
                    self.active = {"attempt_id": payload["attempt_id"], "config": actual, "scenario": payload["scenario"]}
                    self.store.set("active", self.active)
                self.record_stop.clear()
                self.recorder = threading.Thread(target=self.record, daemon=True)
                self.recorder.start()
                self.game = "live"
                result = {"actual": actual}
            elif kind == "stop_session":
                if self.active and self.active["attempt_id"] != payload["attempt_id"]:
                    raise RuntimeError("Polecenie dotyczy nieaktualnej próby")
                had_active = bool(self.active)
                self.stop_recording()
                self.launcher.stop()
                self.finish("interrupted", "Zatrzymano przez instruktora")
                # A prepared session may be cancelled before the game was started.
                if not had_active:
                    self.store.queue(f"/api/agent/attempts/{payload['attempt_id']}/finish", {"status": "interrupted", "config": {}, "note": "Sesja zatrzymana"})
                self.game = "idle"
                result = {"stopped": True}
            elif kind == "hardware_profile":
                if self.active or self.game != "idle" or game_running():
                    raise RuntimeError("Zmiana profilu jest dozwolona tylko przed jazdą")
                result = self.hardware.apply(payload)
            else:
                raise RuntimeError("Agent nie obsługuje tego rodzaju polecenia")
            self.store.result(command_id, "succeeded", result)
            self.error = None
        except Exception as exc:
            log.exception("Nie wykonano %s", kind)
            self.error = str(exc)
            if kind == "start_session":
                try:
                    self.launcher.stop()
                except Exception:
                    log.exception("Konfiguracja wymaga lokalnego przywrócenia")
                self.game = "idle"
            self.store.result(command_id, "failed", {"error": str(exc)})

    def record(self):
        reader = ACReader()
        batch = []
        started = time.monotonic()
        try:
            while not self.record_stop.is_set():
                sample, self.game = reader.read()
                if sample:
                    if not all(math.isfinite(v) for v in sample.values() if isinstance(v, float)):
                        raise RuntimeError("Nieskończone lub niepoprawne wartości telemetrii")
                    self.latest = sample
                    batch.append(sample)
                if len(batch) >= 50:
                    self.upload_later(batch)
                    batch = []
                if self.launcher.process and self.launcher.process.poll() is not None:
                    break
                if self.store.size() > 256 * 1024 * 1024:
                    raise RuntimeError("Bufor offline osiągnął 256 MiB. Nagranie przerwane; jazda pozostaje lokalna")
                time.sleep(.01)
        except Exception as exc:
            self.error = str(exc)
            log.exception("Nagranie przerwane")
        finally:
            reader.close()
            if batch:
                self.upload_later(batch)
            if not self.record_stop.is_set():
                self.finish("interrupted" if self.error else "completed", self.error or "Gra zakończona")
                if self.launcher.process and self.launcher.process.poll() is not None:
                    self.launcher.restore()
                    self.game = "idle"

    def upload_later(self, samples):
        with self.lock:
            if self.active:
                self.store.queue(f"/api/agent/attempts/{self.active['attempt_id']}/telemetry", {"chunk_id": uuid.uuid4().hex, "samples": samples})

    def finish(self, status, note):
        with self.lock:
            if self.active:
                self.store.queue(f"/api/agent/attempts/{self.active['attempt_id']}/finish", {"status": status, "config": self.active["config"], "note": note})
                self.active = None
                self.store.set("active", None)

    def stop_recording(self):
        self.record_stop.set()
        if self.recorder:
            self.recorder.join(timeout=5)
            if self.recorder.is_alive():
                raise RuntimeError("Wątek zapisu nadal pracuje; stan wymaga sprawdzenia")
            self.recorder = None

    def run(self):
        self.store.recover_commands()
        previous = self.store.get("active")
        if previous:
            self.store.queue(f"/api/agent/attempts/{previous['attempt_id']}/finish", {"status": "interrupted", "config": previous["config"], "note": "Agent uruchomiony ponownie; wymagane sprawdzenie gry i konfiguracji"})
            self.store.set("active", None)
        catalog = self.launcher.catalog()
        while not self.shutdown.is_set():
            try:
                if not self.active and (self.future is None or self.future.done()):
                    self.game = "error" if game_running() else "idle"
                    if self.game == "error":
                        self.error = "Gra działa poza bieżącą próbą agenta; zamknij ją i sprawdź konfigurację"
                hardware = self.hardware.snapshot()
                capabilities = ["ac.launch", "ac.multiplayer"]
                if hardware.get("connected"):
                    capabilities.append("hardware.profile")
                response = self.client.post("/api/agent/heartbeat", json={"version": "0.1.0", "game": self.game,
                    "hardware": hardware, "capabilities": capabilities, "catalog": catalog,
                    "active_attempt": self.active["attempt_id"] if self.active else None,
                    "telemetry": self.latest, "error": self.error})
                response.raise_for_status()
                self.flush()
                if self.future is None or self.future.done():
                    response = self.client.get("/api/agent/commands")
                    response.raise_for_status()
                    for command in response.json():
                        previous = self.store.command(command["id"])
                        if previous:
                            if previous["state"] != "running":
                                self.store.result(command["id"], previous["state"], json.loads(previous["result"]))
                            continue
                        self.future = self.pool.submit(self.execute, command)
                        break
            except (httpx.HTTPError, OSError) as exc:
                log.warning("Centrala niedostępna: %s", exc)
            self.shutdown.wait(1)

    def close(self):
        self.shutdown.set()
        self.pool.shutdown(wait=True)
        self.stop_recording()
        try:
            self.launcher.stop()
        except Exception:
            log.exception("Konfiguracja wymaga lokalnego sprawdzenia po zamknięciu agenta")
        self.finish("interrupted", "Agent wyłączony")
        try:
            self.flush()
        except httpx.HTTPError:
            pass
        self.hardware.close()
        self.client.close()
