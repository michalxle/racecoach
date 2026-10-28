"""Odczyt gry w postaci potrzebnej trenerowi (okrążenia, delta, wskazówki).

Pola odpowiadają AcSnapshot z SimTrainer; agent RaceCoach buduje je z tych samych struktur
pamięci współdzielonej AC (shared_memory.Physics/Graphics).
"""
from __future__ import annotations

from dataclasses import dataclass

AC_OFF, AC_REPLAY, AC_LIVE, AC_PAUSE = 0, 1, 2, 3


@dataclass
class AcSnapshot:
    status: int = AC_LIVE
    completed_laps: int = 0
    current_ms: int = 0
    last_ms: int = 0
    best_ms: int = 0
    in_pit: bool = False
    in_pit_lane: bool = False
    speed_kmh: float = 0.0
    gear: int = 1
    gas: float = 0.0
    brake: float = 0.0
    tyres_out: int = 0
    spline: float = 0.0
    x: float = 0.0
    z: float = 0.0
    vx: float | None = None
    vz: float | None = None

    @property
    def gear_display(self) -> int:
        """Bieg dla człowieka: -1 = R, 0 = N, 1… = biegi."""
        return self.gear - 1


def from_memory(physics, graphics) -> AcSnapshot:
    return AcSnapshot(status=graphics.status, completed_laps=graphics.laps, current_ms=graphics.current_ms,
                      last_ms=graphics.last_ms, best_ms=graphics.best_ms, in_pit=bool(graphics.in_pits),
                      in_pit_lane=bool(graphics.in_pitlane), speed_kmh=max(0.0, physics.speed), gear=physics.gear,
                      gas=physics.gas, brake=physics.brake, tyres_out=physics.tyres_out,
                      spline=graphics.progress, x=graphics.coordinates[0], z=graphics.coordinates[2],
                      vx=physics.velocity[0], vz=physics.velocity[2])
