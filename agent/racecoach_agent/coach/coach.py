"""Trener: delta do okrążenia referencyjnego, wykrywanie zakrętów i wskazówki.

Okrążenie referencyjne to najlepsze okrążenie kierowcy (z serwera), rekord
grupy albo najlepsze okrążenie bieżącej sesji. Po każdym okrążeniu porównujemy
je z referencją zakręt po zakręcie:

* strata czasu w zakręcie = przyrost delty od połowy prostej przed zakrętem
  do połowy prostej za nim,
* przyczyna: punkt hamowania, prędkość w szczycie zakrętu (apeksie) albo
  moment otwarcia pełnego gazu na wyjściu.

Wskazówki dostają 1–2 zakręty z największą stratą.
"""

from __future__ import annotations

from dataclasses import dataclass

from .trace import Trace

MIN_DROP_KMH = 12      # spadek prędkości, od którego miejsce traktujemy jako zakręt
MERGE_M = 70           # zakręty bliżej niż tyle metrów łączymy w jeden
BRAKE_ON = 0.12
THROTTLE_FULL = 0.9
MIN_LOSS_MS = 80       # mniejsze straty pomijamy
MAX_TIPS = 2

SOURCE_LABEL = {
    "exercise": "wzorzec ćwiczenia",
    "pb": "rekord osobisty",
    "record": "rekord grupy",
    "session": "najlepsze w sesji",
}


@dataclass
class Corner:
    n: int
    apex: int
    start: int
    end: int
    brake: int | None
    throttle: int | None
    vmin: float

    def to_dict(self, tr: Trace) -> dict:
        return {"n": self.n, "s": round(self.apex / tr.n, 4), "vmin": round(self.vmin, 1)}


def cdiff(a: int, b: int, n: int) -> int:
    """Różnica indeksów a - b na torze zamkniętym, w zakresie (-n/2, n/2]."""
    d = (a - b) % n
    return d - n if d > n // 2 else d


def _smooth(vals: list[float], w: int = 2) -> list[float]:
    n = len(vals)
    return [sum(vals[(i + k) % n] for k in range(-w, w + 1)) / (2 * w + 1) for i in range(n)]


def brake_start(tr: Trace, apex: int, back_m: float = 300) -> int | None:
    """Początek strefy hamowania przed apeksem (None = zakręt bez hamowania)."""
    n = tr.n
    steps = max(1, int(back_m / max(tr.m_per_pt, 0.1)))
    i = apex
    # szukamy wstecz ostatniego punktu z hamowaniem
    found = None
    for k in range(steps):
        j = (apex - k) % n
        if tr.b[j] >= BRAKE_ON:
            found = j
            break
    if found is None:
        return None
    i = found
    for _ in range(steps):
        j = (i - 1) % n
        if tr.b[j] < BRAKE_ON:
            return i
        i = j
    return i


def throttle_point(tr: Trace, apex: int, fwd_m: float = 300) -> int | None:
    n = tr.n
    steps = max(1, int(fwd_m / max(tr.m_per_pt, 0.1)))
    for k in range(steps):
        j = (apex + k) % n
        if tr.g[j] >= THROTTLE_FULL:
            return j
    return None


def find_corners(tr: Trace) -> list[Corner]:
    n = tr.n
    if n < 20 or tr.len_m <= 0:
        return []
    m = tr.m_per_pt
    v = _smooth(tr.v)
    w = max(2, int(20 / m))
    back = max(3, int(250 / m))
    cands: list[int] = []
    for i in range(n):
        vi = v[i]
        # pierwszy punkt „płaskiego dna” (stała prędkość w długim łuku) albo zwykłe minimum
        if vi < v[(i - 1) % n] and all(vi <= v[(i + k) % n] for k in range(-w, w + 1) if k):
            peak = max(v[(i - k) % n] for k in range(1, back))
            if peak - vi >= MIN_DROP_KMH:
                cands.append(i)
    # łączenie bliskich minimów
    merge = max(1, int(MERGE_M / m))
    apexes: list[int] = []
    for i in cands:
        if apexes and abs(cdiff(i, apexes[-1], n)) < merge:
            if v[i] < v[apexes[-1]]:
                apexes[-1] = i
            continue
        apexes.append(i)
    if len(apexes) > 1 and abs(cdiff(apexes[0], apexes[-1], n)) < merge:
        if v[apexes[-1]] < v[apexes[0]]:
            apexes[0] = apexes[-1]
        apexes.pop()
    apexes.sort()
    corners = []
    k = len(apexes)
    for idx, a in enumerate(apexes):
        prev_a = apexes[idx - 1] if k > 1 else a - n // 2
        next_a = apexes[(idx + 1) % k] if k > 1 else a + n // 2
        start = (a + cdiff(prev_a, a, n) // 2) % n if k > 1 else (a - n // 2) % n
        end = (a + cdiff(next_a, a, n) // 2) % n if k > 1 else (a + n // 2 - 1) % n
        corners.append(Corner(n=idx + 1, apex=a, start=start, end=end, brake=brake_start(tr, a),
                              throttle=throttle_point(tr, a), vmin=v[a]))
    return corners


def unwrap_spline(s: float, t_ms: float, ref_ms: float) -> float:
    """Pozycja na torze „ciągła” względem czasu okrążenia (może wyjść poza 0..1)."""
    if s > 0.8 and t_ms < 0.25 * ref_ms:
        return s - 1.0
    if s < 0.2 and t_ms > 0.75 * ref_ms:
        return s + 1.0
    return s


def ref_time_ext(ref: Trace, s: float) -> float:
    """Czas referencji w punkcie s; poza 0..1 – liniowo za linią mety."""
    if s < 0.0:
        return s * ref.time_ms
    if s > 1.0:
        return ref.time_ms * s
    return ref.time_at(s)


def _num(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


class Coach:
    def __init__(self, reference: Trace | None = None, source: str = "session"):
        self.ref: Trace | None = None
        self.source = source
        self.corners: list[Corner] = []
        if reference is not None:
            self.set_reference(reference, source)

    def set_reference(self, ref: Trace, source: str) -> None:
        self.ref = ref
        self.source = source
        self.corners = find_corners(ref)
        ref.meta["corners"] = [c.to_dict(ref) for c in self.corners]
        ref.meta["source"] = source

    @property
    def label(self) -> str:
        return SOURCE_LABEL.get(self.source, self.source)

    def delta(self, s: float, t_ms: float) -> int | None:
        """Delta w miejscu toru s przy czasie okrążenia t_ms.

        Linia pomiaru czasu i zero pozycji na torze (spline) nie leżą dokładnie w tym
        samym miejscu: tuż po przecięciu mety pozycja może jeszcze wynosić 0.99…, a tuż
        przed metą już 0.00…. Bez korekty delta skacze wtedy o cały czas okrążenia.
        """
        ref = self.ref
        if ref is None or not -0.01 <= s <= 1.01:
            return None
        s = unwrap_spline(s, t_ms, ref.time_ms)
        return int(round(t_ms - ref_time_ext(ref, s)))

    def better_than_reference(self, lap_ms: int) -> bool:
        return self.ref is None or lap_ms < self.ref.time_ms

    # ------------------------------------------------------------------ analysis
    def _d(self, lap: Trace, i: int) -> float:
        assert self.ref is not None
        return lap.t[i] - self.ref.t[i]

    def corner_loss(self, lap: Trace, c: Corner) -> float:
        assert self.ref is not None
        if c.start < c.end:
            return self._d(lap, c.end) - self._d(lap, c.start)
        # zakręt „przez linię mety”
        total = lap.time_ms - self.ref.time_ms
        return (total - self._d(lap, c.start)) + (self._d(lap, c.end) - self._d(lap, 0))

    def analyse(self, lap: Trace, valid: bool = True) -> dict:
        """Wskazówki po okrążeniu: {summary, lines: [{corner, loss_ms, text}], delta_ms}."""
        ref = self.ref
        if ref is None or not self.corners:
            return {"summary": "Pierwsze pełne okrążenie zapisane – od następnego pojawią się wskazówki.",
                    "lines": [], "delta_ms": None, "vs": self.label}
        n = ref.n
        m = ref.m_per_pt
        total = lap.time_ms - ref.time_ms
        rows = []
        for c in self.corners:
            loss = self.corner_loss(lap, c)
            rows.append((loss, c))
        lines = []
        if total < 0 and valid:
            gain_loss, gain_c = min(rows, key=lambda r: r[0])
            summary = (f"Lepiej niż {self.label} o {_num(-total / 1000, 3)} s! "
                       f"Najwięcej zyskane w zakręcie {gain_c.n} ({_num(-gain_loss / 1000)} s).")
        else:
            summary = f"{'+' if total >= 0 else '−'}{_num(abs(total) / 1000, 3)} s do: {self.label}."
            if not valid:
                summary += " Okrążenie nieważne (wyjazd poza tor)."
        for loss, c in sorted(rows, key=lambda r: -r[0])[:MAX_TIPS]:
            if loss < MIN_LOSS_MS:
                break
            lines.append({"corner": c.n, "loss_ms": int(loss), "text": self._explain(lap, c, loss, n, m)})
        if not lines and total >= 0:
            summary += " Strata rozłożona równomiernie – bez jednego wyraźnego miejsca."
        return {"summary": summary, "lines": lines, "delta_ms": int(total), "vs": self.label}

    def _explain(self, lap: Trace, c: Corner, loss: float, n: int, m: float) -> str:
        ref = self.ref
        assert ref is not None
        head = f"Zakręt {c.n}, strata {_num(loss / 1000)} s – "
        # pomiary na okrążeniu w okolicy apeksu z referencji
        win = max(2, int(40 / m))
        lap_apex = min(((c.apex + k) % n for k in range(-win, win + 1)), key=lambda i: lap.v[i])
        vmin_lap = lap.v[lap_apex]
        dv = vmin_lap - ref.v[c.apex]
        lap_brake = brake_start(lap, c.apex)
        lap_thr = throttle_point(lap, lap_apex)

        brake_early_m = None
        if c.brake is not None and lap_brake is not None:
            brake_early_m = cdiff(c.brake, lap_brake, n) * m   # >0: hamowanie wcześniej niż w referencji
        thr_late_m = None
        if c.throttle is not None and lap_thr is not None:
            thr_late_m = cdiff(lap_thr, c.throttle, n) * m     # >0: pełny gaz później

        if brake_early_m is not None and brake_early_m >= 8 and dv > -6:
            return head + f"hamujesz ok. {brake_early_m:.0f} m za wcześnie. Przesuń punkt hamowania bliżej zakrętu."
        if dv <= -3:
            if brake_early_m is not None and brake_early_m <= -8:
                return head + (f"za późne hamowanie – w apeksie o {-dv:.0f} km/h wolniej. "
                               "Zacznij hamować wcześniej i wnieś więcej prędkości w zakręt.")
            return head + (f"w apeksie o {-dv:.0f} km/h wolniej niż na najlepszym okrążeniu. "
                           "Puść hamulec wcześniej i płynniej.")
        if thr_late_m is not None and thr_late_m >= 10:
            return head + f"pełny gaz ok. {thr_late_m:.0f} m później. Otwieraj gaz wcześniej na wyjściu."
        if lap_thr is None and c.throttle is not None:
            return head + "na wyjściu brak pełnego gazu. Wyprostuj kierownicę i dodaj gazu."
        return head + "tracisz na całej długości zakrętu – sprawdź tor jazdy i płynność."
