"""Sesja trenera na stanowisku: z kolejnych odczytów gry liczy okrążenia, deltę i wskazówki.

Wynikiem są: stan dla nakładek (odświeżany przy każdym odczycie) oraz zdarzenia okrążeń
wysyłane do centrali (czas, ważność, wyjazdy, wskazówki, przebieg ważnego okrążenia).
Wzorzec do delty: wzorzec ćwiczenia → rekord kursanta → najlepsze okrążenie sesji;
w trakcie jazdy przesuwa się na każde szybsze ważne okrążenie.
"""
from __future__ import annotations

import logging
import threading
import time

from .coach import SOURCE_LABEL, Coach
from .laps import LapTracker
from .snapshot import AC_LIVE, AC_PAUSE, AcSnapshot
from .trace import LapRecorder, Trace, build_trace

log = logging.getLogger("racecoach.coach")


class LiveSession:
    def __init__(self, attempt_id, *, reference=None, info=None, race_laps=None, pb_ms=None):
        self.attempt_id = attempt_id
        self.info = dict(info or {})
        self.race_laps = race_laps
        self.tracker = LapTracker()
        self.recorder = LapRecorder()
        ref, source = None, "session"
        if reference and reference.get("trace"):
            try:
                ref, source = Trace.from_dict(reference["trace"]), reference.get("source", "pb")
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Nieczytelny przebieg wzorcowy: %s", exc)
        self.coach = Coach(ref, source)
        self.reference_id = 1 if ref else 0
        self.lock = threading.Lock()
        self.events = []
        self.session_best = None
        self.pb_ms = pb_ms
        self.last_ms, self.last_valid = None, True
        self.tips = None
        self.message = None
        self.offtracks = 0
        self.live = {}
        self.state = "launching"
        self.finished = False

    # ------------------------------------------------------------------ odczyty gry
    def process(self, snap: AcSnapshot):
        if snap.status == AC_PAUSE:
            self.state = "paused"
            return
        if snap.status != AC_LIVE:
            return
        self.recorder.add(snap)
        laps, offtracks = self.tracker.update(snap)
        self.offtracks += offtracks
        for lap in laps:
            self._on_lap(lap, snap)
        fast = not (snap.in_pit or snap.in_pit_lane or self.tracker.lap_from_pit)
        delta = self.coach.delta(snap.spline, snap.current_ms) if fast else None
        with self.lock:
            self.state = "in_pit" if snap.in_pit or snap.in_pit_lane else "on_track"
            self.live = {"laps": snap.completed_laps, "lap_no": self.tracker.lap_no, "current_ms": snap.current_ms,
                         "delta_ms": delta, "spline": round(snap.spline, 5), "speed_kmh": round(snap.speed_kmh, 1),
                         "gear": snap.gear_display, "gas": round(snap.gas, 2), "brake": round(snap.brake, 2),
                         "x": round(snap.x, 2), "z": round(snap.z, 2),
                         "vx": None if snap.vx is None else round(snap.vx, 2),
                         "vz": None if snap.vz is None else round(snap.vz, 2),
                         "tyres_out": snap.tyres_out, "t": int(time.monotonic() * 1000)}

    def _on_lap(self, lap, snap):
        trace = build_trace(self.recorder.take_finished(), lap.time_ms)
        analysis = self.coach.analyse(trace, lap.valid) if trace is not None else None
        if lap.valid and (self.session_best is None or lap.time_ms < self.session_best):
            self.session_best = lap.time_ms
        if lap.valid and (self.pb_ms is None or lap.time_ms < self.pb_ms):
            self.pb_ms = lap.time_ms
        if trace is not None and lap.valid and self.coach.better_than_reference(lap.time_ms):
            source = self.coach.source if self.coach.ref is not None else "session"
            self.coach.set_reference(trace, source)
            self.reference_id += 1
        event = {"lap_no": lap.lap_no, "lap": max(0, self.tracker._completed - 1), "time_ms": lap.time_ms,
                 "valid": lap.valid, "offtracks": lap.offtracks, "reason": lap.reason,
                 "tips": analysis or {}, "trace": trace.to_dict() if trace is not None and lap.valid else None}
        with self.lock:
            self.last_ms, self.last_valid = lap.time_ms, lap.valid
            if analysis:
                self.tips = {"lap_no": lap.lap_no, **analysis}
            self.events.append(event)
            if self.race_laps and lap.lap_no >= self.race_laps:
                self.finished = True

    # ------------------------------------------------------------------ dla agenta i nakładek
    def take_events(self):
        with self.lock:
            events, self.events = self.events, []
        return events

    def set_message(self, text):
        with self.lock:
            self.message = {"id": time.time(), "text": text}

    def reference(self):
        ref = self.coach.ref
        if ref is None:
            return None
        data = ref.to_dict()
        return {"id": self.reference_id, "label": self.coach.label, **data}

    def summary(self):
        """Krótki stan do panelu instruktora (w sygnale życia agenta)."""
        with self.lock:
            return {"state": self.state, "lap_no": self.tracker.lap_no, "current_ms": self.live.get("current_ms"),
                    "delta_ms": self.live.get("delta_ms"), "last_ms": self.last_ms, "last_valid": self.last_valid,
                    "best_ms": self.session_best, "pb_ms": self.pb_ms, "offtracks": self.offtracks,
                    "ref_label": self.coach.label if self.coach.ref else None, "tips": self.tips,
                    "race_laps": self.race_laps, "finished": self.finished}

    def overlay_state(self):
        with self.lock:
            return {"active": True, "state": self.state, "session": self.info,
                    "live": {**self.live, "last_ms": self.last_ms, "last_valid": self.last_valid,
                             "best_ms": self.session_best},
                    "pb_ms": self.pb_ms, "offtracks": self.offtracks,
                    "ref": {"id": self.reference_id, "label": SOURCE_LABEL.get(self.coach.source, "")} if self.coach.ref else None,
                    "tips": self.tips, "message": self.message,
                    "race": {"laps": self.race_laps, "done": self.finished} if self.race_laps else None}
