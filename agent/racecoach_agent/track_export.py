"""Export local track geometry; no game assets are bundled with RaceCoach."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def export_track(game_dir, track, layout="", name=None, sections=6):
    root = (Path(game_dir) / "content/tracks").resolve()
    folder = (root / track / layout).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Niepoprawna ścieżka toru")
    path = folder / "ai/fast_lane.ai"
    if not path.is_file():
        raise ValueError("Tor nie ma fast_lane.ai. Użyj nagrania współrzędnych albo przygotuj pakiet JSON ręcznie")
    data = path.read_bytes()
    version, count, _, _ = struct.unpack_from("<4i", data)
    if version != 7 or not 3 <= count <= 1000000 or len(data) < 16 + count * 20:
        raise ValueError("Nieobsługiwany lub uszkodzony format linii AI")
    points = [struct.unpack_from("<4fi", data, 16 + i * 20) for i in range(count)]
    if not all(math.isfinite(v) for p in points for v in p[:4]):
        raise ValueError("Niepoprawne współrzędne linii AI")
    length = sum(math.dist(a[:3], b[:3]) for a, b in zip(points, points[1:]))
    if length <= 10:
        raise ValueError("Niepoprawna długość trasy")
    stride = max(1, count // 1200)
    geometry = [[p[0], p[2]] for p in points[::stride]]
    if geometry[-1] != [points[-1][0], points[-1][2]]:
        geometry.append([points[-1][0], points[-1][2]])
    return {"id": track + ("--" + layout if layout else ""), "game_id": track, "name": name or track,
            "layout": layout, "length": length, "geometry": geometry,
            "sections": [{"id": str(i + 1), "name": f"Sekcja {i + 1}", "start": i / sections, "end": (i + 1) / sections} for i in range(sections)],
            "version": hashlib.sha256(data).hexdigest()[:16], "source": "ai"}


def main():
    parser = argparse.ArgumentParser(description="Eksport geometrii toru AC do importu w RaceCoach")
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--layout", default="")
    parser.add_argument("--name")
    parser.add_argument("--sections", type=int, default=6, choices=range(1, 61))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = export_track(args.game_dir, args.track, args.layout, args.name, args.sections)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Zapisano pakiet toru. Zweryfikuj granice sekcji względem postępu raportowanego przez grę.")


if __name__ == "__main__":
    main()
