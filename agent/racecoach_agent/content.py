"""Katalog treści stanowiska z czytelnymi nazwami (auta, tory z wariantami, pogoda).

Nazwy pochodzą z plików gry: ui/ui_car.json, ui/ui_track.json (lub ui/<wariant>/ui_track.json)
i content/weather/<id>/weather.ini. Pliki ui_*.json bywają niepoprawnym JSON-em (znaki
sterujące, wieloliniowe opisy), więc są czytane łagodnie.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import re
from pathlib import Path


def read_ui(path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return {}
    try:
        data = json.loads(text, strict=False)
        return data if isinstance(data, dict) else {}
    except ValueError:
        result = {}
        for key in ("name", "brand", "class", "length", "country"):
            match = re.search(r'"%s"\s*:\s*"([^"]*)"' % key, text)
            if match:
                result[key] = match.group(1)
        return result


def _text(value, fallback=""):
    return str(value).strip() if isinstance(value, (str, int, float)) and str(value).strip() else fallback


def _length(value):
    match = re.search(r"[\d.,]+", str(value or ""))
    if not match:
        return None
    number = float(match.group(0).replace(",", "."))
    return round(number * 1000) if number < 50 else round(number)  # "5.79 km" albo "5793"


def weather_name(folder):
    parser = configparser.ConfigParser(strict=False, interpolation=None, inline_comment_prefixes=(";",))
    try:
        parser.read_string((folder / "weather.ini").read_text(encoding="utf-8", errors="ignore"))
        return parser.get("LAUNCHER", "NAME", fallback="").strip() or folder.name
    except (OSError, configparser.Error):
        return folder.name


def _has_data(folder):
    return (folder / "data").is_dir() or (folder / "data.acd").is_file()


def scan(game_dir):
    game_dir = Path(game_dir)
    cars, tracks, weather = [], [], []
    root = game_dir / "content/cars"
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()) if root.is_dir() else []:
        ui = read_ui(folder / "ui/ui_car.json")
        skins = folder / "skins"
        cars.append({"id": folder.name, "name": _text(ui.get("name"), folder.name), "brand": _text(ui.get("brand")),
                     "class": _text(ui.get("class")),
                     "skins": sum(1 for p in skins.iterdir() if p.is_dir()) if skins.is_dir() else 0})
    root = game_dir / "content/tracks"
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()) if root.is_dir() else []:
        variants = []
        if _has_data(folder):
            variants.append(("", folder, folder / "ui/ui_track.json"))
        for layout in sorted(p for p in folder.iterdir() if p.is_dir()):
            if _has_data(layout):
                variants.append((layout.name, layout, folder / "ui" / layout.name / "ui_track.json"))
        base = read_ui(folder / "ui/ui_track.json")
        for layout, path, ui_file in variants:
            ui = read_ui(ui_file) if layout else base
            name = _text(ui.get("name"), (folder.name + " " + layout).strip())
            tracks.append({"id": folder.name, "layout": layout, "name": name,
                           "track_name": _text(base.get("name"), name.split(" - ")[0]),
                           "length_m": _length(ui.get("length")), "country": _text(ui.get("country")),
                           "has_ai": (path / "ai/fast_lane.ai").is_file(), "has_map": (path / "map.png").is_file()})
    root = game_dir / "content/weather"
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()) if root.is_dir() else []:
        weather.append({"id": folder.name, "name": weather_name(folder)})
    content = {"cars": cars, "tracks": tracks, "weather": weather}
    content["hash"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    return content
