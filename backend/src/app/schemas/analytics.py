"""Persisted analytics, not live occupancy or cross-camera identity."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from ai_detector_core.telemetry.analytics import TrackSession


class EventCount(BaseModel):
    key: str
    count: int


class CameraStatistics(BaseModel):
    camera_id: UUID
    name: str
    archived: bool
    enabled: bool
    events: int
    observed_seconds: float
    average_persons: float | None
    max_persons: int | None
    completed_tracks: int


class TimeBucket(BaseModel):
    at: AwareDatetime
    events: int


class PeopleBucket(BaseModel):
    at: AwareDatetime
    persons: float
    persons_in_zone: float
    samples: int


class Dashboard(BaseModel):
    generated_at: AwareDatetime
    start: AwareDatetime
    end: AwareDatetime
    camera_id: UUID | None
    total_events: int
    critical_events: int
    false_positives: int
    active_cameras: int | None = None
    enabled_cameras: int
    average_events_per_camera: float | None
    completed_tracks: int
    by_type: list[EventCount]
    by_camera: list[CameraStatistics]
    events_over_time: list[TimeBucket]
    people_over_time: list[PeopleBucket]
    bucket_seconds: int


class TrackPage(BaseModel):
    items: list[TrackSession]
    next_cursor: str | None
