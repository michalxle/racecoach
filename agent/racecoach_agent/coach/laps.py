"""Wykrywanie ukończonych okrążeń i wyjazdów poza tor z kolejnych odczytów Shared Memory."""

from __future__ import annotations

from dataclasses import dataclass

from .snapshot import AC_LIVE, AcSnapshot

# Zasada AC (ALLOWED_TYRES_OUT=2): więcej niż 2 koła poza torem = wyjazd.
MAX_TYRES_OUT = 2
# Ile odczytów czekać na aktualizację iLastTime po zmianie completedLaps.
LAST_TIME_WAIT_SAMPLES = 5


@dataclass
class LapEvent:
    lap_no: int
    time_ms: int
    valid: bool
    offtracks: int
    reason: str = ""  # dlaczego nieważne: "poza torem", "boks"


class LapTracker:
    def __init__(self, count_offtrack_laps: bool = False) -> None:
        # True: wyjazd poza tor (ścięcie) nie unieważnia okrążenia – czas się liczy,
        # a liczba wyjazdów nadal trafia do wyniku (ustawienie z panelu admina)
        self.count_offtrack_laps = count_offtrack_laps
        self.reset()

    def reset(self) -> None:
        self._completed: int | None = None
        self._last_ms_seen = 0
        self._pending: int | None = None   # numer okrążenia czekający na iLastTime
        self._pending_wait = 0
        self._lap_invalid = False   # unieważnione przez boks
        self._lap_reason = ""
        self._lap_offtracks = 0
        self._was_out = False
        self.lap_no = 0
        self.lap_from_pit = False   # bieżące okrążenie zaczęło się w boksie / alei serwisowej

    def update(self, s: AcSnapshot) -> tuple[list[LapEvent], int]:
        """Zwraca (ukończone okrążenia, liczba nowych wyjazdów poza tor)."""
        laps: list[LapEvent] = []
        new_offtracks = 0
        if s.status != AC_LIVE:
            return laps, 0

        if self._completed is None or s.completed_laps < self._completed:
            # pierwszy odczyt albo restart sesji w grze
            self._completed = s.completed_laps
            self._last_ms_seen = s.last_ms
            self._pending = None
            self._start_lap(s, first=True)
            return laps, 0

        # wyjazdy poza tor w trakcie okrążenia
        out = s.tyres_out > MAX_TYRES_OUT
        if out and not self._was_out:
            self._lap_offtracks += 1
            new_offtracks += 1
        self._was_out = out
        if s.in_pit_lane or s.in_pit:
            self._invalidate("boks")
            self.lap_from_pit = True

        if s.completed_laps > self._completed and self._pending is None:
            self._pending = s.completed_laps
            self._pending_wait = 0
            self._finished_flags = (self._lap_invalid, self._lap_reason, self._lap_offtracks)
            self._completed = s.completed_laps
            # nowe okrążenie zaczyna się od zera
            self._start_lap(s)

        if self._pending is not None:
            self._pending_wait += 1
            if s.last_ms != self._last_ms_seen or self._pending_wait >= LAST_TIME_WAIT_SAMPLES:
                invalid, reason, offtracks = self._finished_flags
                if offtracks and not invalid and not self.count_offtrack_laps:
                    invalid, reason = True, "poza torem"
                if s.last_ms > 0:
                    self.lap_no += 1
                    laps.append(LapEvent(self.lap_no, s.last_ms, not invalid, offtracks, reason if invalid else ""))
                self._last_ms_seen = s.last_ms
                self._pending = None
        return laps, new_offtracks

    def _start_lap(self, s: AcSnapshot, first: bool = False) -> None:
        self._lap_invalid = False
        self._lap_reason = ""
        self._lap_offtracks = 0
        self.lap_from_pit = s.in_pit or s.in_pit_lane
        if first and self.lap_from_pit:
            self._invalidate("boks")  # okrążenie wyjazdowe z boksu
        self._was_out = s.tyres_out > MAX_TYRES_OUT

    def _invalidate(self, reason: str) -> None:
        if not self._lap_invalid:
            self._lap_reason = reason
        self._lap_invalid = True
