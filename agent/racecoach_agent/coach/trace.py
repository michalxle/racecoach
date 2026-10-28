"""Przebieg okrążenia („trace”): czas, prędkość, gaz, hamulec i pozycja wzdłuż toru.

Okrążenie jest zapisywane jako próbki z gry, a po jego ukończeniu
przeliczane na N punktów równomiernie rozłożonych wzdłuż toru (pozycja
0..1 z ``normalizedCarPosition``). Dzięki temu dwa okrążenia można porównać
punkt po punkcie: delta w danym miejscu toru to różnica czasów w tym punkcie.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field

from .snapshot import AC_LIVE, AcSnapshot

N_POINTS = 500

# Wystarczające pokrycie toru, żeby przebieg był użyteczny
MIN_START_S = 0.04
MIN_END_S = 0.96
MIN_SAMPLES = 40


@dataclass
class Sample:
    s: float
    t: float
    v: float
    g: float
    b: float
    x: float
    z: float


@dataclass
class Trace:
    """Okrążenie przeliczone na N punktów; punkt i leży na pozycji s = i / N."""

    time_ms: int
    t: list[float]   # czas od linii mety [ms]
    v: list[float]   # prędkość [km/h]
    g: list[float]   # gaz 0..1
    b: list[float]   # hamulec 0..1
    x: list[float]
    z: list[float]
    len_m: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.t)

    @property
    def m_per_pt(self) -> float:
        return self.len_m / self.n if self.n else 0.0

    def time_at(self, s: float) -> float:
        """Czas (ms) w punkcie toru s ∈ [0, 1] – interpolacja liniowa."""
        n = self.n
        s = min(max(s, 0.0), 1.0)
        pos = s * n
        i = int(pos)
        if i >= n:
            return float(self.time_ms)
        t0 = self.t[i]
        t1 = self.t[i + 1] if i + 1 < n else float(self.time_ms)
        return t0 + (t1 - t0) * (pos - i)

    def to_dict(self) -> dict:
        r1 = lambda xs: [round(v, 1) for v in xs]  # noqa: E731
        r2 = lambda xs: [round(v, 2) for v in xs]  # noqa: E731
        return {
            "n": self.n, "time_ms": self.time_ms, "len_m": round(self.len_m, 1),
            "t": [int(round(v)) for v in self.t], "v": r1(self.v), "g": r2(self.g), "b": r2(self.b),
            "x": r1(self.x), "z": r1(self.z), "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Trace":
        return cls(time_ms=int(d["time_ms"]), t=[float(v) for v in d["t"]], v=list(d["v"]), g=list(d["g"]),
                   b=list(d["b"]), x=list(d["x"]), z=list(d["z"]), len_m=float(d.get("len_m", 0)),
                   meta=dict(d.get("meta") or {}))


class LapRecorder:
    """Zbiera próbki bieżącego okrążenia; po przekroczeniu mety odkłada je do odbioru."""

    def __init__(self) -> None:
        self.samples: list[Sample] = []
        self._completed: int | None = None
        self._finished: list[Sample] | None = None

    def add(self, snap: AcSnapshot) -> None:
        if snap.status != AC_LIVE:
            return
        if self._completed is None:
            self._completed = snap.completed_laps
        if snap.completed_laps != self._completed:
            if snap.completed_laps > self._completed:
                self._finished = self.samples
            self.samples = []
            self._completed = snap.completed_laps
        s = snap.spline
        t = float(snap.current_ms)
        # Linia mety i zero pozycji toru nie leżą dokładnie w tym samym miejscu:
        # tuż po starcie okrążenia pozycja może jeszcze wynosić 0.99…, a tuż przed
        # metą już 0.00…
        if t < 15_000 and s > 0.8:
            s -= 1.0
        elif self.samples and self.samples[-1].s > 0.8 and s < 0.2:
            s += 1.0
        if self.samples and s <= self.samples[-1].s:
            return  # cofanie się / postój – pomijamy
        self.samples.append(Sample(s, t, snap.speed_kmh, snap.gas, snap.brake, snap.x, snap.z))

    def take_finished(self) -> list[Sample] | None:
        out, self._finished = self._finished, None
        return out


def build_trace(samples: list[Sample] | None, time_ms: int, n: int = N_POINTS) -> Trace | None:
    """Przelicza próbki na n punktów; None, jeśli okrążenie jest niepełne."""
    if not samples or len(samples) < MIN_SAMPLES:
        return None
    if samples[0].s > MIN_START_S or samples[-1].s < MIN_END_S:
        return None
    ss = [p.s for p in samples]
    out = {k: [] for k in ("t", "v", "g", "b", "x", "z")}
    for i in range(n):
        target = i / n
        j = bisect_right(ss, target)
        if j == 0:
            a = bb = samples[0]
            f = 0.0
        elif j >= len(samples):
            a = bb = samples[-1]
            f = 0.0
        else:
            a, bb = samples[j - 1], samples[j]
            f = (target - a.s) / (bb.s - a.s) if bb.s > a.s else 0.0
        for k in out:
            va, vb = getattr(a, k), getattr(bb, k)
            out[k].append(va + (vb - va) * f)
    # czas musi rosnąć i mieścić się w czasie okrążenia
    t = out["t"]
    t[0] = max(0.0, t[0]) if t[0] < 15_000 else 0.0
    for i in range(1, n):
        if t[i] < t[i - 1]:
            t[i] = t[i - 1]
    for i in range(n):
        t[i] = min(t[i], float(time_ms))
    length = 0.0
    xs, zs = out["x"], out["z"]
    for i in range(n):
        j = (i + 1) % n
        length += math.hypot(xs[j] - xs[i], zs[j] - zs[i])
    return Trace(time_ms=int(time_ms), len_m=length, **out)
