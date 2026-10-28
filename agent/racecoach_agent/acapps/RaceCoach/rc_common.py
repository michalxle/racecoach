# Wspólny kod aplikacji RaceCoach w Assetto Corsa (Python 3.3 – bez f-stringów).
#
# Agent RaceCoach zapisuje w tym folderze:
#   overlay.json   – wiadomość i cel od instruktora, wskazówki po okrążeniu, najlepszy czas
#   reference.json – okrążenie referencyjne: czasy i pozycje wzdłuż toru, zakręty
# Aplikacje czytają te pliki, a deltę i minimapę liczą same w każdej klatce
# z pozycji auta na torze (NormalizedSplinePosition) i czasu okrążenia.

import json
import os

BASE = os.path.join("apps", "python", "RaceCoach")

ACCENT = (0.91, 0.47, 0.26, 1.0)
GREEN = (0.24, 0.84, 0.55, 1.0)
RED = (1.0, 0.42, 0.42, 1.0)
WHITE = (0.95, 0.96, 0.97, 1.0)
GREY = (0.68, 0.71, 0.74, 1.0)


class JsonFile:
    """Plik JSON wczytywany ponownie tylko po zmianie."""

    def __init__(self, name):
        self.path = os.path.join(BASE, name)
        self.mtime = None
        self.data = None

    def poll(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m == self.mtime:
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self.mtime = m
            return True
        except Exception:
            return False


class Reference:
    def __init__(self, d):
        self.t = d["t"]
        self.x = d["x"]
        self.z = d["z"]
        self.n = len(self.t)
        self.time_ms = float(d["time_ms"])
        self.len_m = float(d.get("len_m") or 1.0)
        self.corners = d.get("corners") or []
        self.label = d.get("label") or ""

    def time_at(self, s):
        s = min(max(s, 0.0), 1.0)
        pos = s * self.n
        i = int(pos)
        if i >= self.n:
            return self.time_ms
        t1 = self.t[i + 1] if i + 1 < self.n else self.time_ms
        return self.t[i] + (t1 - self.t[i]) * (pos - i)

    def point(self, i):
        i %= self.n
        return self.x[i], self.z[i]

    def point_at(self, s):
        pos = (s % 1.0) * self.n
        i = int(pos) % self.n
        j = (i + 1) % self.n
        f = pos - int(pos)
        return (self.x[i] + (self.x[j] - self.x[i]) * f, self.z[i] + (self.z[j] - self.z[i]) * f)


def load_reference(rf):
    """Zwraca Reference albo None (rf = JsonFile("reference.json"))."""
    d = rf.data
    if not d or d.get("none") or "t" not in d:
        return None
    try:
        return Reference(d)
    except Exception:
        return None


def unwrap_spline(s, t_ms, ref_ms):
    """Linia mety i zero pozycji toru nie pokrywają się – bez tej korekty delta skacze
    przy mecie o cały czas okrążenia."""
    if s > 0.8 and t_ms < 0.25 * ref_ms:
        return s - 1.0
    if s < 0.2 and t_ms > 0.75 * ref_ms:
        return s + 1.0
    return s


def delta_ms(ref, s, t_ms):
    s = unwrap_spline(s, t_ms, ref.time_ms)
    if s < 0.0:
        ref_t = s * ref.time_ms
    elif s > 1.0:
        ref_t = ref.time_ms * s
    else:
        ref_t = ref.time_at(s)
    return t_ms - ref_t


def read_map_ini(path):
    """Parametry z data/map.ini toru (bez configparsera – AC ma okrojoną bibliotekę)."""
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.split(";")[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    try:
                        out[k.strip().upper()] = float(v.strip())
                    except ValueError:
                        pass
    except OSError:
        return None
    return out if out.get("SCALE_FACTOR") else None


def track_map_paths(track, layout):
    base = os.path.join("content", "tracks", track)
    if layout:
        base = os.path.join(base, layout)
    return os.path.join(base, "map.png"), os.path.join(base, "data", "map.ini")


def fmt_delta(ms):
    sign = "+" if ms >= 0 else "-"
    return "{}{:.2f}".format(sign, abs(ms) / 1000.0)


def fmt_ms(ms):
    if not ms or ms <= 0:
        return "-"
    ms = int(ms)
    return "{}:{:02d}.{:03d}".format(ms // 60000, (ms % 60000) // 1000, ms % 1000)


def wrap(text, width):
    words = (text or "").split()
    lines, line = [], ""
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)
    return lines


def plain(text):
    """AC nie zawsze ma czcionkę z polskimi znakami – zamieniamy je na łacińskie."""
    table = {"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z",
             "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z",
             "–": "-", "—": "-", "−": "-"}
    return "".join(table.get(c, c) for c in (text or ""))


# ---------------------------------------------------------------- wygląd okienek
# Tylko podstawowe, sprawdzone funkcje API AC: bez własnych czcionek (initFont/setCustomFont)
# i bez glBegin/glVertex – te potrafią wywrócić całą grę, a nie tylko aplikację.


def style_window(window, w, h):
    """Ciemne okienko bez ramki, tytułu i ikony AC – jak nakładki w przeglądarce."""
    ac_mod = __import__("ac")
    ac_mod.setSize(window, w, h)
    ac_mod.setTitle(window, "")
    ac_mod.drawBorder(window, 0)
    try:
        ac_mod.setBackgroundColor(window, 0.04, 0.05, 0.06)
    except Exception:
        pass
    ac_mod.setBackgroundOpacity(window, 0.84)


def label(window, text, x, y, size, color=WHITE, w=None, align=None, bold=False):
    ac_mod = __import__("ac")
    lab = ac_mod.addLabel(window, text)
    ac_mod.setPosition(lab, x, y)
    ac_mod.setFontSize(lab, size)
    ac_mod.setFontColor(lab, *color)
    if w is not None:
        ac_mod.setSize(lab, w, size + 6)
    if align:
        ac_mod.setFontAlignment(lab, align)
    return lab


_logged = set()


def log_error(app, where):
    """Zapisuje błąd aplikacji do Dokumenty/Assetto Corsa/logs/py_log.txt (każdy rodzaj raz)."""
    import traceback
    text = traceback.format_exc()
    key = (app, where, text[-200:])
    if key in _logged:
        return
    _logged.add(key)
    try:
        __import__("ac").log("[{}] blad w {}: {}".format(app, where, text))
    except Exception:
        pass


# ---------------------------------------------------------------- układ z panelu RaceCoach
class Layout:
    """Położenie i widoczność okienka ustawione w nakładkach w przeglądarce (/overlay/N).

    Agent zapisuje je w overlay.json jako {"layout": {"id", "pos": {okno: {x, y}}, "off": {okno: bool}},
    "screen": {"w", "h"}}; x i y to ułamki szerokości/wysokości ekranu gry. Układ jest stosowany
    tylko przy zmianie, więc okienko nadal można przesunąć myszą w grze.
    """

    def __init__(self, widget_id):
        self.widget_id = widget_id
        self.applied = None
        self.desktop = None

    def apply(self, window, data):
        # Gdy działają nakładki RaceCoach nad grą (osobne okno), te aplikacje się chowają,
        # żeby nic się nie dublowało; po zakończeniu sesji wracają.
        desktop = bool((data or {}).get("desktop_overlay"))
        if desktop != self.desktop:
            if desktop or self.desktop:          # nie włączamy okna, którego nikt nie chował
                try:
                    __import__("ac").setVisible(window, 0 if desktop else 1)
                except Exception:
                    pass
            self.desktop = desktop
            self.applied = None
        if desktop:
            return
        layout = (data or {}).get("layout") or {}
        lid = layout.get("id")
        if not lid or lid == self.applied:
            return
        self.applied = lid
        ac_mod = __import__("ac")
        screen = (data or {}).get("screen") or {}
        sw, sh = float(screen.get("w") or 1920), float(screen.get("h") or 1080)
        pos = (layout.get("pos") or {}).get(self.widget_id)
        if pos:
            try:
                ac_mod.setPosition(window, int(pos["x"] * sw), int(pos["y"] * sh))
            except Exception:
                pass
        off = (layout.get("off") or {}).get(self.widget_id)
        try:
            ac_mod.setVisible(window, 0 if off else 1)
        except Exception:
            pass


# ---------------------------------------------------------------- linia AI toru (geometria)
def read_fast_lane(track, layout):
    """Punkty (x, z) linii AI z content/tracks/<tor>/[<wariant>/]ai/fast_lane.ai albo None.

    Format: nagłówek 4 × int32 (wersja, liczba punktów, czas, liczba próbek), potem dla każdego
    punktu 3 × float pozycji, float długości i int32 numeru (20 bajtów).
    """
    import struct
    base = os.path.join("content", "tracks", track)
    if layout:
        base = os.path.join(base, layout)
    path = os.path.join(base, "ai", "fast_lane.ai")
    try:
        with open(path, "rb") as f:
            data = f.read()
        version, count, _lap, _samples = struct.unpack_from("<4i", data, 0)
        if count < 50 or count > 200000 or len(data) < 16 + 20 * count:
            return None
        pts = []
        for i in range(count):
            x, _y, z, _length, _idx = struct.unpack_from("<4fi", data, 16 + 20 * i)
            pts.append((x, z))
    except Exception:
        return None
    # kontrola sensu: sąsiednie punkty blisko siebie
    bad = 0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dz = pts[i][1] - pts[i - 1][1]
        if dx * dx + dz * dz > 50 * 50:
            bad += 1
    if bad > 3:
        return None
    # rzadziej: co ok. 3 m
    step = 1
    total = 0.0
    for i in range(1, min(len(pts), 200)):
        total += ((pts[i][0] - pts[i - 1][0]) ** 2 + (pts[i][1] - pts[i - 1][1]) ** 2) ** 0.5
    avg = total / max(1, min(len(pts), 200) - 1)
    if avg > 0:
        step = max(1, int(3.0 / avg))
    return pts[::step]
