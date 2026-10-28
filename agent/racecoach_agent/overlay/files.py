"""Pliki gry potrzebne nakładkom: mapa toru, ustawienia ekranu i aplikacje RaceCoach w AC.

Aplikacje Python w Assetto Corsie (folder acapps) czytają z apps/python/RaceCoach dwa pliki
zapisywane przez agenta: overlay.json (cel, wiadomość, wskazówki, czasy, układ okienek) i
reference.json (wzorzec do delty i minimapy). Działają także przy pełnym ekranie wyłącznym,
gdy okno nakładek nad grą nie może być widoczne.
"""
from __future__ import annotations

import configparser
import json
import logging
import shutil
import time
from pathlib import Path

log = logging.getLogger("racecoach.overlay")
APPS = Path(__file__).resolve().parent.parent / "acapps"
MAP_KEYS = ("WIDTH", "HEIGHT", "MARGIN", "SCALE_FACTOR", "X_OFFSET", "Z_OFFSET", "DRAWING_SIZE")


def install_apps(game_dir):
    """Kopiuje aplikacje RaceCoach do <gra>/apps/python (tylko zmienione pliki)."""
    installed = []
    for source in sorted(p for p in APPS.iterdir() if p.is_dir()):
        target = Path(game_dir) / "apps/python" / source.name
        try:
            target.mkdir(parents=True, exist_ok=True)
            for file in source.glob("*.py"):
                destination = target / file.name
                if not destination.exists() or destination.read_bytes() != file.read_bytes():
                    shutil.copyfile(file, destination)
            installed.append(target)
        except OSError as exc:
            log.warning("Nie udało się zainstalować aplikacji %s: %s", source.name, exc)
    return installed


def parse_map_ini(text):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    section = parser["PARAMETERS"] if parser.has_section("PARAMETERS") else {}
    out = {}
    for key in MAP_KEYS:
        try:
            out[key] = float(str(section.get(key, "0")).split(";")[0].strip() or 0)
        except ValueError:
            out[key] = 0.0
    return out


def track_map(game_dir, track, layout=""):
    """{'png': ścieżka, 'ini': parametry} mapy z gry (jak aplikacja „Map” w AC) albo None."""
    base = Path(game_dir) / "content/tracks" / track
    if layout:
        base = base / layout
    png, ini = base / "map.png", base / "data/map.ini"
    try:
        params = parse_map_ini(ini.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, configparser.Error):
        return None
    if not png.is_file() or not params.get("SCALE_FACTOR"):
        return None
    return {"png": png, "ini": params}


def _video(documents):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string((Path(documents) / "cfg/video.ini").read_text(encoding="utf-8", errors="ignore"))
    except (OSError, configparser.Error):
        return None
    return parser


def screen_size(documents):
    parser = _video(documents)
    try:
        w, h = int(float(parser.get("VIDEO", "WIDTH"))), int(float(parser.get("VIDEO", "HEIGHT")))
        if w > 0 and h > 0:
            return {"w": w, "h": h}
    except (AttributeError, configparser.Error, ValueError):
        pass
    return {"w": 1920, "h": 1080}


def exclusive_fullscreen(documents):
    """Pełny ekran wyłączny (video.ini FULLSCREEN=1) przykrywa każde okno – zostają aplikacje w grze."""
    parser = _video(documents)
    try:
        return int(float(parser.get("VIDEO", "FULLSCREEN"))) != 0
    except (AttributeError, configparser.Error, ValueError):
        return False


class AppFiles:
    """Zapis plików czytanych przez aplikacje RaceCoach w grze."""

    def __init__(self, game_dir, documents):
        self.folder = Path(game_dir) / "apps/python/RaceCoach"
        self.documents = documents
        self.last = None
        self.reference_id = None

    def _write(self, name, data):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            temporary = self.folder / (name + ".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.folder / name)
        except OSError as exc:
            log.debug("Nie można zapisać %s: %s", name, exc)

    def update(self, state, reference, desktop_overlay):
        live = state.get("live") or {}
        session = state.get("session") or {}
        data = {"goal": session.get("goal") or session.get("exercise") or "", "message": state.get("message"),
                "tips": state.get("tips"), "best_ms": live.get("best_ms"), "pb_ms": state.get("pb_ms"),
                "ref_label": (state.get("ref") or {}).get("label", ""), "layout": state.get("layout") or {},
                "screen": screen_size(self.documents), "desktop_overlay": bool(desktop_overlay)}
        if data != self.last:
            self.last = data
            self._write("overlay.json", {**data, "id": time.time()})
        rid = (reference or {}).get("id")
        if rid != self.reference_id:
            self.reference_id = rid
            if reference:
                self._write("reference.json", {"id": time.time(), "time_ms": reference["time_ms"], "len_m": reference["len_m"],
                                               "t": reference["t"], "x": reference["x"], "z": reference["z"],
                                               "corners": reference.get("meta", {}).get("corners", []), "label": reference.get("label", "")})
            else:
                self._write("reference.json", {"id": time.time(), "none": True})
