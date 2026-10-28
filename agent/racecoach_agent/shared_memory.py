"""Read-only AC 1.x SDK layout. UTF-16 types keep offsets portable in tests.

The named mappings are opened, never created. This module is not the ACC SDK.
"""
from __future__ import annotations

import ctypes as C
import os

I, F = C.c_int32, C.c_float
S15, S33 = C.c_uint16 * 15, C.c_uint16 * 33
V3, V4 = F * 3, F * 4


def text(array):
    return bytes(array).decode("utf-16-le").split("\0", 1)[0]


class Physics(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("packet_id", I), ("gas", F), ("brake", F), ("fuel", F), ("gear", I), ("rpm", I),
                ("steer", F), ("speed", F), ("velocity", V3), ("acceleration", V3),
                ("wheel_slip", V4), ("wheel_load", V4), ("wheel_pressure", V4), ("wheel_angular", V4),
                ("tyre_wear", V4), ("tyre_dirt", V4), ("tyre_temp", V4), ("camber", V4), ("suspension", V4),
                ("drs", F), ("tc", F), ("heading", F), ("pitch", F), ("roll", F), ("cg_height", F),
                ("damage", F * 5), ("tyres_out", I)]


class Graphics(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("packet_id", I), ("status", I), ("session", I), ("current_time", S15), ("last_time", S15),
                ("best_time", S15), ("split", S15), ("laps", I), ("position", I), ("current_ms", I), ("last_ms", I),
                ("best_ms", I), ("time_left", F), ("distance", F), ("in_pits", I), ("sector", I), ("last_sector_ms", I),
                ("number_of_laps", I), ("tyre_compound", S33), ("replay_multiplier", F), ("progress", F),
                ("coordinates", V3), ("penalty_time", F), ("flag", I), ("ideal_line", I), ("in_pitlane", I), ("grip", F)]


class Static(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("shared_version", S15), ("game_version", S15), ("sessions", I), ("cars", I), ("car", S33), ("track", S33),
                ("first_name", S33), ("surname", S33), ("nickname", S33), ("sectors", I),
                ("max_torque", F), ("max_power", F), ("max_rpm", I), ("max_fuel", F), ("suspension_max", V4),
                ("tyre_radius", V4), ("max_turbo", F), ("air_temp", F), ("road_temp", F), ("penalties", I),
                ("fuel_rate", F), ("tyre_rate", F), ("damage_rate", F), ("tyre_blankets", I), ("stability", F),
                ("auto_clutch", I), ("auto_blip", I), ("has_drs", I), ("has_ers", I), ("has_kers", I), ("kers_max", F),
                ("engine_brakes", I), ("ers_controllers", I), ("spline_length", F), ("layout", C.c_uint16 * 15)]


class NamedMapping:
    def __init__(self, name, structure):
        if os.name != "nt":
            raise OSError("Odczyt pamięci Assetto Corsa wymaga Windows")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenFileMappingW.argtypes = [C.c_uint32, C.c_int, C.c_wchar_p]
        self.kernel.OpenFileMappingW.restype = C.c_void_p
        self.kernel.MapViewOfFile.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_size_t]
        self.kernel.MapViewOfFile.restype = C.c_void_p
        self.kernel.UnmapViewOfFile.argtypes = [C.c_void_p]
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.structure = structure
        self.handle = self.kernel.OpenFileMappingW(4, False, "Local\\" + name)
        if not self.handle:
            raise OSError("Gra nie udostępnia jeszcze " + name)
        self.pointer = self.kernel.MapViewOfFile(self.handle, 4, 0, 0, C.sizeof(structure))
        if not self.pointer:
            self.kernel.CloseHandle(self.handle)
            raise OSError("Nie można odczytać " + name)

    def read(self):
        for _ in range(3):
            before = C.string_at(self.pointer, 4)
            data = C.string_at(self.pointer, C.sizeof(self.structure))
            if before == data[:4] == C.string_at(self.pointer, 4):
                return self.structure.from_buffer_copy(data)
        raise OSError("Niespójny pakiet pamięci gry")

    def close(self):
        if getattr(self, "pointer", None):
            self.kernel.UnmapViewOfFile(self.pointer)
            self.pointer = None
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class ACReader:
    def __init__(self):
        self.maps = []
        self.last_packet = None
        self.lap = None
        self.completed_time = 0
        self.seq = 0

    def connect(self):
        if self.maps:
            return
        try:
            for name, structure in (("acpmf_physics", Physics), ("acpmf_graphics", Graphics), ("acpmf_static", Static)):
                self.maps.append(NamedMapping(name, structure))
        except OSError:
            self.close()
            raise

    def identity(self):
        self.connect()
        static = self.maps[2].read()
        return {"track_id": text(static.track), "layout": text(static.layout), "car": text(static.car),
                "game_version": text(static.game_version), "shared_version": text(static.shared_version),
                "simulated": False, "assists": {"stability": static.stability, "auto_clutch": static.auto_clutch},
                "spline_length": static.spline_length}

    def read(self):
        self.connect()
        physics, graphics = self.maps[0].read(), self.maps[1].read()
        if graphics.status != 2:  # OFF=0, REPLAY=1, LIVE=2, PAUSE=3
            return None, "paused" if graphics.status == 3 else "idle"
        if physics.packet_id == self.last_packet:
            return None, "live"
        if self.lap is not None and graphics.laps < self.lap:
            raise RuntimeError("Gra zresetowała okrążenie; rozpocznij nową próbę")
        if self.lap is not None and graphics.laps > self.lap:
            if graphics.laps != self.lap + 1 or graphics.last_ms <= 0:
                raise RuntimeError("Utracono granicę okrążenia; próba wymaga nowego nagrania")
            self.completed_time += graphics.last_ms / 1000
        self.lap = graphics.laps
        self.last_packet = physics.packet_id
        sample = {"seq": self.seq, "t": self.completed_time + graphics.current_ms / 1000,
                  "lap": graphics.laps, "progress": min(1, max(0, graphics.progress)),
                  "x": graphics.coordinates[0], "y": graphics.coordinates[1], "z": graphics.coordinates[2],
                  "speed": max(0, physics.speed), "throttle": min(1, max(0, physics.gas)), "brake": min(1, max(0, physics.brake)),
                  "steer": physics.steer, "gear": physics.gear - 1, "rpm": max(0, physics.rpm),
                  "valid": not (graphics.in_pitlane or graphics.in_pits or physics.tyres_out > 2)}
        self.seq += 1
        return sample, "live"

    def close(self):
        for mapping in self.maps:
            mapping.close()
        self.maps = []
