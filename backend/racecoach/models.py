from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Login(Model):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class TraineeCreate(Model):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    notes: str = Field(default="", max_length=4000)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if "@" not in value or any(c.isspace() for c in value):
            raise ValueError("Podaj poprawny adres e-mail")
        return value


class PlanCreate(Model):
    trainee_id: str
    title: str = Field(min_length=2, max_length=150)


class PlanItemCreate(Model):
    exercise_id: str
    title: str = Field(min_length=2, max_length=150)
    goal: str = Field(min_length=3, max_length=2000)
    criteria: str = Field(default="Ocena instruktora", max_length=2000)
    mode: Literal["individual", "multiplayer", "either"] = "either"
    scheduled: str | None = None

    @field_validator("scheduled")
    @classmethod
    def date_valid(cls, value):
        if value:
            from datetime import date
            date.fromisoformat(value)
        return value


class PlanItemUpdate(Model):
    status: Literal["planned", "ready", "repeat", "passed", "skipped"]
    note: str = Field(default="", max_length=4000)


class Conditions(Model):
    weather: str = Field(default="3_clear", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    air_temp: float = Field(default=22, ge=-10, le=50)
    road_temp: float = Field(default=29, ge=-10, le=80)
    grip: float = Field(default=1, ge=0.5, le=1)
    rain: float = Field(default=0, ge=0, le=1)
    time: str = Field(default="13:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class HardwareProfile(Model):
    degrees: int = Field(ge=180, le=1440)
    strength: int = Field(ge=0, le=100)


class ExerciseReference(Model):
    attempt_id: str
    lap: int = Field(ge=0)


class ExerciseCreate(Model):
    title: str = Field(min_length=2, max_length=150)
    track_id: str
    car: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    conditions: Conditions = Field(default_factory=Conditions)
    duration: int = Field(default=15, ge=1, le=180)
    mode: Literal["individual", "multiplayer", "either"] = "either"
    hardware_profile: HardwareProfile | None = None


class StationCreate(Model):
    name: str = Field(min_length=2, max_length=100)


class Participant(Model):
    trainee_id: str
    station_id: str
    plan_item_id: str | None = None


class RunCreate(Model):
    exercise_id: str
    mode: Literal["individual", "multiplayer"]
    participants: list[Participant] = Field(min_length=1, max_length=24)
    race_laps: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def unique_participants(self):
        if self.mode == "individual" and len(self.participants) != 1:
            raise ValueError("Sesja indywidualna wymaga jednego uczestnika")
        for key in ("trainee_id", "station_id"):
            values = [getattr(p, key) for p in self.participants]
            if len(set(values)) != len(values):
                raise ValueError("Kursant i stanowisko mogą wystąpić tylko raz")
        return self


class Heartbeat(Model):
    version: str = Field(max_length=40)
    game: Literal["idle", "starting", "live", "paused", "error"] = "idle"
    hardware: dict = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list, max_length=30)
    catalog: list[str] = Field(default_factory=list, max_length=10000)
    active_attempt: str | None = None
    telemetry: dict | None = None
    coach: dict | None = None
    error: str | None = Field(default=None, max_length=2000)


class CommandResult(Model):
    status: Literal["accepted", "running", "succeeded", "failed", "rejected", "unknown"]
    result: dict = Field(default_factory=dict)


class Sample(Model):
    seq: int = Field(ge=0)
    t: float = Field(ge=0)
    lap: int = Field(ge=0)
    progress: float = Field(ge=0, le=1)
    x: float
    y: float = 0
    z: float
    speed: float = Field(ge=0, le=1500)
    throttle: float = Field(ge=0, le=1)
    brake: float = Field(ge=0, le=1)
    steer: float = Field(ge=-20, le=20)
    gear: int = Field(ge=-1, le=20)
    rpm: float = Field(ge=0, le=50000)
    valid: bool = True


class TelemetryBatch(Model):
    chunk_id: str = Field(min_length=1, max_length=100)
    samples: list[Sample] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def ordered(self):
        for a, b in zip(self.samples, self.samples[1:]):
            if b.seq <= a.seq or b.t < a.t:
                raise ValueError("Próbki muszą mieć rosnący numer i niemalejący czas")
        return self


class AttemptFinish(Model):
    status: Literal["completed", "interrupted", "failed"]
    config: dict = Field(default_factory=dict)
    note: str = Field(default="", max_length=4000)


class AttemptReview(Model):
    note: str = Field(max_length=4000)
    decision: Literal["none", "passed", "repeat"] = "none"


class Section(Model):
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=100)
    start: float = Field(ge=0, lt=1)
    end: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start:
            raise ValueError("Koniec sekcji musi być za początkiem")
        return self


class LapEvent(Model):
    lap_no: int = Field(ge=1, le=100000)
    lap: int = Field(ge=0, le=100000)
    time_ms: int = Field(gt=0, le=24 * 3600 * 1000)
    valid: bool
    offtracks: int = Field(default=0, ge=0, le=10000)
    reason: str = Field(default="", max_length=100)
    tips: dict = Field(default_factory=dict)
    trace: dict | None = None


class MessageIn(Model):
    text: str = Field(min_length=1, max_length=300)


class OverlayLayout(Model):
    pos: dict[str, dict[str, float]] = Field(default_factory=dict)
    off: dict[str, bool] = Field(default_factory=dict)


class StationContent(Model):
    cars: list[dict] = Field(default_factory=list, max_length=5000)
    tracks: list[dict] = Field(default_factory=list, max_length=5000)
    weather: list[dict] = Field(default_factory=list, max_length=500)
    hash: str = Field(max_length=64)


class TrackFromGame(Model):
    track: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    layout: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_.-]*$")
    sections: int = Field(default=6, ge=1, le=60)


class TrackCreate(Model):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    game_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=150)
    layout: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_.-]*$")
    length: float = Field(gt=10, lt=1000000)
    geometry: list[Annotated[list[float], Field(min_length=2, max_length=2)]] = Field(min_length=3, max_length=20000)
    sections: list[Section] = Field(min_length=1, max_length=60)
    version: str = Field(min_length=1, max_length=100)
    source: Literal["recorded", "ai", "imported", "demo"] = "imported"

    @model_validator(mode="after")
    def sections_valid(self):
        ids = [s.id for s in self.sections]
        if len(set(ids)) != len(ids):
            raise ValueError("Identyfikatory sekcji muszą być unikalne")
        ordered = sorted(self.sections, key=lambda s: s.start)
        for a, b in zip(ordered, ordered[1:]):
            if b.start < a.end:
                raise ValueError("Sekcje nie mogą się nakładać")
        return self


class WeatherChange(Model):
    rain: float = Field(ge=0, le=1)
    wetness: float = Field(ge=0, le=1)
    water: float = Field(ge=0, le=1)
    transition: float = Field(default=30, ge=0, le=600)
