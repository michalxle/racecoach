"""Katalog treści stanowisk (auta, tory, pogoda z nazwami) i automatyczny import toru.

Agent wysyła katalog po starcie i przy każdej zmianie zawartości gry. Przy tworzeniu scenariusza
panel pokazuje sumę katalogów stanowisk; wybrany tor, którego geometrii centrala jeszcze nie ma,
jest eksportowany przez agenta z linii AI gry (polecenie export_track) i zapisywany jak import ręczny.
"""
from __future__ import annotations

import json
import time

from fastapi import Depends, HTTPException

from .app import instructor, station, user
from .db import dump
from .models import StationContent, TrackCreate, TrackFromGame


def wait_command(db, command_id, timeout):
    """Czeka na wynik polecenia stanowiska; zwraca wiersz polecenia albo None po czasie."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = db.one("SELECT status,result FROM commands WHERE id=?", (command_id,))
        if row["status"] in ("succeeded", "failed", "rejected", "unknown", "expired"):
            return {"status": row["status"], "result": json.loads(row["result"])}
        time.sleep(.2)
    return None


def merged_content(db):
    cars, tracks, weather = {}, {}, {}
    rows = db.all("SELECT id,name,content,last_seen FROM stations WHERE simulated=0")
    for row in rows:
        content = json.loads(row["content"] or "{}")
        online = row["last_seen"] is not None and time.time() - row["last_seen"] < 12
        for car in content.get("cars", []):
            entry = cars.setdefault(car["id"], {**car, "stations": []})
            entry["stations"].append(row["id"])
        for track in content.get("tracks", []):
            entry = tracks.setdefault((track["id"], track.get("layout", "")), {**track, "stations": [], "online": False})
            entry["stations"].append(row["id"])
            entry["online"] = entry["online"] or online
        for item in content.get("weather", []):
            weather.setdefault(item["id"], item)
    imported = {(t["game_id"] or t["id"], t["layout"]): t["id"] for t in db.all("SELECT id,game_id,layout FROM tracks ORDER BY rowid")}
    for key, entry in tracks.items():
        entry["track_id"] = imported.get(key)
    return {"cars": sorted(cars.values(), key=lambda c: c["name"].lower()),
            "tracks": sorted(tracks.values(), key=lambda t: t["name"].lower()),
            "weather": sorted(weather.values(), key=lambda w: w["id"])}


def register_content_routes(app, db):
    @app.post("/api/agent/content")
    def upload_content(body: StationContent, source=Depends(station)):
        with db.transaction() as c:
            c.execute("UPDATE stations SET content=? WHERE id=?", (dump(body.model_dump()), source["id"]))
        return {"ok": True, "hash": body.hash}

    @app.get("/api/content")
    def content(actor=Depends(user)):
        return merged_content(db)

    @app.post("/api/content/tracks")
    def track_from_game(body: TrackFromGame, actor=Depends(instructor)):
        """Zwraca tor gotowy do scenariusza; w razie potrzeby eksportuje go na stanowisku."""
        existing = db.one("SELECT id FROM tracks WHERE COALESCE(game_id,id)=? AND layout=? AND source!='demo' ORDER BY rowid DESC LIMIT 1",
                          (body.track, body.layout))
        if existing:
            return {"id": existing["id"], "imported": False}
        entry = next((t for t in merged_content(db)["tracks"] if t["id"] == body.track and t.get("layout", "") == body.layout), None)
        if not entry:
            raise HTTPException(404, "Żadne stanowisko nie zgłosiło tego toru")
        if not entry.get("has_ai"):
            raise HTTPException(422, "Tor nie ma linii AI (ai/fast_lane.ai); przygotuj mapę i zaimportuj ją ręcznie")
        online = [s for s in db.all("SELECT id,last_seen FROM stations WHERE simulated=0") if s["id"] in entry["stations"]
                  and s["last_seen"] and time.time() - s["last_seen"] < 12]
        if not online:
            raise HTTPException(409, "Stanowisko z tym torem jest offline; uruchom agenta i spróbuj ponownie")
        from .training import enqueue
        with db.transaction() as c:
            command_id = enqueue(c, online[0]["id"], "export_track", {"track": body.track, "layout": body.layout,
                                                                     "name": entry["name"], "sections": body.sections}, ttl=40)
        result = wait_command(db, command_id, 35)
        if result is None:
            raise HTTPException(504, "Stanowisko nie odesłało mapy toru w 35 s; sprawdź dziennik poleceń")
        if result["status"] != "succeeded":
            raise HTTPException(409, "Eksport toru nie powiódł się: " + str(result["result"].get("error", "brak szczegółów")))
        track = TrackCreate.model_validate({**result["result"]["track"], "source": "ai"})
        if db.one("SELECT id FROM tracks WHERE id=?", (track.id,)):
            track.id = (track.id + "-" + track.version[:6])[:100]
        with db.transaction() as c:
            c.execute("INSERT OR IGNORE INTO tracks(id,name,layout,length,geometry,sections,version,source,game_id) VALUES (?,?,?,?,?,?,?,?,?)",
                      (track.id, track.name, track.layout, track.length, dump(track.geometry), dump([s.model_dump() for s in track.sections]),
                       track.version, track.source, track.game_id or body.track))
            db.audit(actor["id"], "track.import", track.id, {"version": track.version, "from": online[0]["id"]}, c)
        return {"id": track.id, "imported": True}
