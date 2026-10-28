from __future__ import annotations

import bisect
import hashlib
import json
import time
import zlib

from fastapi import HTTPException

from .db import dump


def store_chunk(db, attempt_id, chunk_id, samples):
    raw = dump(samples).encode()
    checksum = hashlib.sha256(raw).hexdigest()
    with db.transaction() as c:
        previous = c.execute("SELECT checksum FROM telemetry_chunks WHERE attempt_id=? AND chunk_id=?", (attempt_id, chunk_id)).fetchone()
        if previous:
            if previous[0] != checksum:
                raise HTTPException(409, "Ten identyfikator porcji zawiera inne dane")
            return False
        attempt = c.execute("SELECT last_seq,status FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if not attempt:
            raise HTTPException(404, "Nie znaleziono próby")
        if samples[0]["seq"] <= attempt["last_seq"]:
            raise HTTPException(409, "Porcje telemetrii muszą być wysyłane w kolejności")
        c.execute("INSERT INTO telemetry_chunks VALUES (?,?,?,?,?,?,?,?)", (attempt_id, chunk_id, samples[0]["seq"], samples[-1]["seq"], len(samples), checksum, zlib.compress(raw), time.time()))
        c.execute("UPDATE attempts SET last_seq=? WHERE id=?", (samples[-1]["seq"], attempt_id))
    return True


def load_samples(db, attempt_id):
    rows = db.all("SELECT data FROM telemetry_chunks WHERE attempt_id=? ORDER BY first_seq", (attempt_id,))
    result = []
    for row in rows:
        result.extend(json.loads(zlib.decompress(row["data"])))
    return result


def interpolate(samples, progress):
    positions = [p["progress"] for p in samples]
    i = bisect.bisect_left(positions, progress)
    if i == 0:
        return samples[0]
    if i == len(samples):
        return samples[-1]
    a, b = samples[i - 1], samples[i]
    ratio = (progress - a["progress"]) / max(1e-12, b["progress"] - a["progress"])
    keys = ("t", "x", "y", "z", "speed", "throttle", "brake", "steer", "rpm")
    return {**a, **{k: a[k] + (b[k] - a[k]) * ratio for k in keys}, "progress": progress}


def split_laps(samples):
    groups = {}
    for index, current in enumerate(samples):
        if index:
            before = samples[index - 1]
            gap = current["progress"] + 1 - before["progress"]
            if current["lap"] == before["lap"] + 1 and before["progress"] > .95 and current["progress"] < .05 and 0 < gap < .05 and current["t"] - before["t"] < .5:
                fraction = (1 - before["progress"]) / gap
                boundary = {**before, "t": before["t"] + fraction * (current["t"] - before["t"]), "progress": 1.0}
                groups.setdefault(before["lap"], []).append(boundary)
                groups.setdefault(current["lap"], []).append({**boundary, "lap": current["lap"], "progress": 0.0})
        groups.setdefault(current["lap"], []).append(current)
    result = []
    for lap, points in sorted(groups.items()):
        monotonic = all(b["progress"] >= a["progress"] - .0001 for a, b in zip(points, points[1:]))
        gap = max((b["t"] - a["t"] for a, b in zip(points, points[1:])), default=0)
        position_gap = max((b["progress"] - a["progress"] for a, b in zip(points, points[1:])), default=0)
        complete = len(points) > 10 and points[0]["progress"] <= .002 and points[-1]["progress"] >= .998 and monotonic
        usable = complete and gap <= .5 and position_gap <= .04 and all(p["valid"] for p in points)
        result.append({"lap": lap, "duration": points[-1]["t"] - points[0]["t"], "complete": complete,
                       "usable": usable, "samples": len(points), "max_gap": gap,
                       "validity": "telemetry_only", "points": points})
    return result


def select_lap(laps, number=None):
    usable = [lap for lap in laps if lap["usable"]]
    if number is not None:
        found = next((lap for lap in usable if lap["lap"] == number), None)
        if found:
            return found
        raise HTTPException(422, "Wybrane okrążenie jest niepełne albo ma niewiarygodne dane")
    if not usable:
        raise HTTPException(422, "Brak pełnego okrążenia z ciągłymi danymi do porównania")
    return min(usable, key=lambda lap: lap["duration"])


def section_metrics(points, section):
    start, end = section["start"], section["end"]
    a, b = interpolate(points, start), interpolate(points, end)
    inside = [a] + [p for p in points if start < p["progress"] < end] + [b]
    # Two consecutive samples above threshold reduce noise from a single reading.
    braking = next((p["progress"] for p, q in zip(inside, inside[1:]) if p["brake"] >= .05 and q["brake"] >= .05), None)
    return {"duration": b["t"] - a["t"], "entry_speed": a["speed"], "min_speed": min(p["speed"] for p in inside),
            "exit_speed": b["speed"], "brake_start": braking, "peak_brake": max(p["brake"] for p in inside)}


def analyze(current, reference, sections, length):
    values = []
    accumulated = 0.0
    for section in sections:
        own = section_metrics(current["points"], section)
        target = section_metrics(reference["points"], section)
        delta = own["duration"] - target["duration"]
        accumulated += delta
        values.append({**section, "current": own, "reference": target, "delta": delta, "accumulated": accumulated,
                       "brake_difference_m": (own["brake_start"] - target["brake_start"]) * length
                       if own["brake_start"] is not None and target["brake_start"] is not None else None})
    def plot(lap):
        points = lap["points"]
        stride = max(1, len(points) // 1600)
        chosen = points[::stride]
        if chosen[-1] is not points[-1]:
            chosen.append(points[-1])
        return [{**p, "t": p["t"] - points[0]["t"], "distance": p["progress"] * length} for p in chosen]
    return {"sections": values, "current": plot(current), "reference": plot(reference),
            "duration": current["duration"], "reference_duration": reference["duration"],
            "delta": current["duration"] - reference["duration"],
            "lap": current["lap"], "reference_lap": reference["lap"],
            "quality": {"current_samples": current["samples"], "reference_samples": reference["samples"],
                        "max_gap": max(current["max_gap"], reference["max_gap"]), "validity": "telemetry_only"}}
