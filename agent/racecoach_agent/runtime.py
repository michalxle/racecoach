from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import os
import subprocess
import sys

import httpx

from . import content as game_content
from .coach.session import LiveSession
from .coach.snapshot import from_memory
from .launcher import game_running
from .overlay import files as overlay_files
from .overlay import window as overlay_window
from .overlay.server import OverlayServer
from .shared_memory import ACReader

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
    def __init__(self, server, token, store, launcher, hardware, overlay_port=31399, overlay_window=True, kiosk=False):
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
        # Trener i nakładki
        self.coach = None
        self.idle_message = None
        self.overlay_layout = {}
        self.track_map = None
        self.content = None
        self.overlay_port, self.overlay_window, self.kiosk = overlay_port, overlay_window, kiosk
        self.overlay_proc = None
        self.overlay = OverlayServer(self.overlay_state, self.reference, lambda: (self.track_map or {}).get("png"), overlay_port)
        self.app_files = overlay_files.AppFiles(launcher.game_dir, launcher.documents) if hasattr(launcher, "game_dir") else None

    # ------------------------------------------------------------------ nakładki
    def overlay_state(self):
        coach = self.coach
        if coach:
            state = coach.overlay_state()
            if state.get("message") is None:
                state["message"] = self.idle_message
        else:
            state = {"active": False, "state": self.game, "session": {}, "live": {}, "message": self.idle_message}
        state["layout"] = self.overlay_layout
        state["map"] = {"url": "/map.png", "ini": self.track_map["ini"]} if coach and self.track_map else None
        return state

    def reference(self):
        return self.coach.reference() if self.coach else None

    def start_overlay(self, scenario):
        game_dir = self.launcher.game_dir
        self.track_map = overlay_files.track_map(game_dir, scenario["track_id"], scenario.get("layout", ""))
        overlay_files.install_apps(game_dir)
        if self.kiosk and os.name == "nt":
            try:
                subprocess.Popen(["cmd", "/c", "start", "msedge", "--kiosk", f"http://127.0.0.1:{self.overlay_port}/kiosk",
                                  "--edge-kiosk-type=fullscreen"], creationflags=0x08000000)
            except OSError:
                log.warning("Nie udało się otworzyć ekranu stanowiska w Edge")
        if not self.overlay_window or os.name != "nt" or self.overlay.httpd is None:
            return
        if overlay_files.exclusive_fullscreen(self.launcher.documents):
            log.warning("Gra działa w pełnym ekranie wyłącznym (video.ini FULLSCREEN=1) – nakładki pokażą aplikacje RaceCoach w grze")
            return
        if not overlay_window.available():
            log.warning("Brak PySide6 – nakładki nad grą niedostępne; działają aplikacje RaceCoach w grze")
            return
        self.stop_overlay()
        url = f"http://127.0.0.1:{self.overlay_port}/?gra=1"
        self.overlay_proc = subprocess.Popen([sys.executable, "-m", "racecoach_agent.overlay.window", url],
                                             creationflags=0x08000000 if os.name == "nt" else 0)
        log.info("Nakładki nad grą: %s", url)

    def stop_overlay(self):
        proc, self.overlay_proc = self.overlay_proc, None
        if proc and proc.poll() is None:
            proc.terminate()

    def sync_app_files(self):
        if self.app_files is None:
            return
        try:
            desktop = self.overlay_proc is not None and self.overlay_proc.poll() is None
            self.app_files.update(self.overlay_state(), self.reference(), desktop)
        except Exception:
            log.debug("Aplikacje w grze: nie udało się zapisać stanu", exc_info=True)

    def queue_laps(self):
        coach = self.coach
        if not coach:
            return
        for event in coach.take_events():
            self.store.queue(f"/api/agent/attempts/{coach.attempt_id}/laps", event)

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
                coach = payload.get("coach") or {}
                info = coach.get("info") or {}
                self.coach = LiveSession(payload["attempt_id"], reference=coach.get("reference"), info=info,
                                         race_laps=coach.get("race_laps") or payload["scenario"].get("race_laps"),
                                         pb_ms=coach.get("pb_ms"))
                actual = self.launcher.start(payload["scenario"], info.get("trainee") or "Kursant RaceCoach")
                actual["hardware"] = self.hardware.snapshot()
                with self.lock:
                    self.active = {"attempt_id": payload["attempt_id"], "config": actual, "scenario": payload["scenario"]}
                    self.store.set("active", self.active)
                self.record_stop.clear()
                self.recorder = threading.Thread(target=self.record, daemon=True)
                self.recorder.start()
                self.game = "live"
                try:
                    self.start_overlay(payload["scenario"])
                except Exception:
                    log.exception("Nakładki nie wystartowały; jazda trwa bez nich")
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
            elif kind == "message":
                text = str(payload.get("text", ""))[:300]
                if self.coach:
                    self.coach.set_message(text)
                self.idle_message = {"id": time.time(), "text": text}
                self.sync_app_files()
                result = {"shown": True}
            elif kind == "export_track":
                from .track_export import export_track
                result = {"track": export_track(self.launcher.game_dir, payload["track"], payload.get("layout", ""),
                                                payload.get("name"), int(payload.get("sections", 6)))}
            elif kind == "set_weather":
                if not self.active or self.active["attempt_id"] != payload.get("attempt_id"):
                    raise RuntimeError("Zmiana pogody dotyczy nieaktywnej próby")
                if not self.launcher.weather_active:
                    raise RuntimeError("Ta sesja nie ma aktywnego kontrolera pogody CSP")
                values = [max(0.0, min(1.0, float(payload[k]))) for k in ("rain", "wetness", "water")]
                result = self.launcher.weather.change(*values, transition=float(payload.get("transition", 30)))
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
                self.coach = None
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
        race_done_at = None
        race_done = False
        try:
            while not self.record_stop.is_set():
                sample, self.game = reader.read()
                coach = self.coach
                if coach and reader.graphics is not None and (sample or self.game == "paused"):
                    coach.process(from_memory(reader.physics, reader.graphics))
                    self.queue_laps()
                    if coach.finished:
                        # Wyścig: po przejechaniu zadanej liczby okrążeń chwila na metę, potem koniec sesji.
                        race_done_at = race_done_at or time.monotonic()
                        if time.monotonic() - race_done_at > 5:
                            race_done = True
                            break
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
                self.finish("interrupted" if self.error else "completed",
                            self.error or ("Wyścig ukończony" if race_done else "Gra zakończona"))
                if race_done:
                    try:
                        self.launcher.stop()
                    except Exception:
                        log.exception("Konfiguracja wymaga lokalnego przywrócenia po wyścigu")
                    self.game = "idle"
                elif self.launcher.process and self.launcher.process.poll() is not None:
                    self.launcher.restore()
                    self.game = "idle"

    def upload_later(self, samples):
        with self.lock:
            if self.active:
                self.store.queue(f"/api/agent/attempts/{self.active['attempt_id']}/telemetry", {"chunk_id": uuid.uuid4().hex, "samples": samples})

    def finish(self, status, note):
        with self.lock:
            self.queue_laps()  # okrążenia przed zakończeniem próby, w tej samej kolejce
            self.coach = None
            self.track_map = None
            self.stop_overlay()
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
        def scan_content():
            try:
                self.content = game_content.scan(self.launcher.game_dir)
            except OSError:
                log.exception("Nie udało się odczytać katalogu treści gry")
            overlay_files.install_apps(self.launcher.game_dir)
        # Skan wszystkich aut i torów trwa chwilę; stanowisko zgłasza się od razu, katalog dochodzi później.
        threading.Thread(target=scan_content, daemon=True, name="content-scan").start()
        self.overlay.start()
        while not self.shutdown.is_set():
            try:
                if not self.active and (self.future is None or self.future.done()):
                    self.game = "error" if game_running() else "idle"
                    if self.game == "error":
                        self.error = "Gra działa poza bieżącą próbą agenta; zamknij ją i sprawdź konfigurację"
                hardware = self.hardware.snapshot()
                capabilities = ["ac.launch", "ac.multiplayer"]
                if self.launcher.weather.available():
                    capabilities.append("weather.csp")
                if hardware.get("connected"):
                    capabilities.append("hardware.profile")
                coach = self.overlay_state() if self.coach else None
                if coach:
                    coach.pop("layout", None)
                    coach.pop("map", None)
                response = self.client.post("/api/agent/heartbeat", json={"version": "0.2.0", "game": self.game,
                    "hardware": hardware, "capabilities": capabilities, "catalog": catalog,
                    "active_attempt": self.active["attempt_id"] if self.active else None,
                    "telemetry": self.latest, "coach": coach, "error": self.error})
                response.raise_for_status()
                reply = response.json()
                self.overlay_layout = reply.get("overlay") or {}
                if self.content and reply.get("content_hash") != self.content["hash"]:
                    self.client.post("/api/agent/content", json=self.content).raise_for_status()
                    log.info("Wysłano katalog treści gry (%d aut, %d torów)", len(self.content["cars"]), len(self.content["tracks"]))
                self.sync_app_files()
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
        self.stop_overlay()
        self.overlay.stop()
