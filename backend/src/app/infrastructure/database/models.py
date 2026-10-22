"""SQLAlchemy models. Schema documentation: docs/database.md."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class CameraModel(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("source_type IN ('file', 'rtsp', 'mock')", name="source_type"),
        Index(
            "uq_cameras_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    assigned_worker: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CameraConfigModel(Base):
    __tablename__ = "camera_configs"
    __table_args__ = (
        CheckConstraint(
            "zone_enter_dwell_seconds >= 0 AND zone_enter_dwell_seconds <= 3600",
            name="zone_enter_dwell_seconds_range",
        ),
        CheckConstraint(
            "zone_exit_grace_seconds >= 0 AND zone_exit_grace_seconds <= 3600",
            name="zone_exit_grace_seconds_range",
        ),
        CheckConstraint(
            "event_cooldown_seconds >= 0 AND event_cooldown_seconds <= 3600",
            name="event_cooldown_seconds_range",
        ),
        CheckConstraint("target_fps >= 1 AND target_fps <= 30", name="target_fps_range"),
        CheckConstraint(
            "detection_confidence > 0 AND detection_confidence <= 1", name="confidence_range"
        ),
    )

    zone_enter_dwell_seconds: Mapped[float | None] = mapped_column(Float)

    zone_exit_grace_seconds: Mapped[float | None] = mapped_column(Float)

    event_cooldown_seconds: Mapped[float | None] = mapped_column(Float)

    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_enabled: Mapped[bool | None] = mapped_column(Boolean)
    target_fps: Mapped[float | None] = mapped_column(Float)
    detection_confidence: Mapped[float | None] = mapped_column(Float)


class ZoneModel(Base):
    __tablename__ = "zones"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(points) = 'array' AND jsonb_array_length(points) BETWEEN 3 AND 64",
            name="points_count",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    points: Mapped[list[dict[str, float]]] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LineModel(Base):
    __tablename__ = "lines"
    __table_args__ = (
        CheckConstraint(
            "p1_x BETWEEN 0 AND 1 AND p1_y BETWEEN 0 AND 1 "
            "AND p2_x BETWEEN 0 AND 1 AND p2_y BETWEEN 0 AND 1",
            name="coordinates",
        ),
        CheckConstraint(
            "(p1_x-p2_x)*(p1_x-p2_x)+(p1_y-p2_y)*(p1_y-p2_y) > 1e-12", name="distinct_endpoints"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    p1_x: Mapped[float] = mapped_column(Float)
    p1_y: Mapped[float] = mapped_column(Float)
    p2_x: Mapped[float] = mapped_column(Float)
    p2_y: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventModel(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("status IN ('NEW', 'ACKNOWLEDGED', 'FALSE_POSITIVE')", name="status"),
        CheckConstraint("severity IN ('critical', 'warning', 'info')", name="severity"),
        Index("ix_events_occurred_at", "occurred_at"),
        Index("ix_events_camera_time", "camera_id", "occurred_at"),
        Index("ix_events_status_time", "status", "occurred_at"),
        Index("ix_events_type_time", "type", "occurred_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    track_id: Mapped[int] = mapped_column(Integer)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="NEW")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_ts_ms: Mapped[float] = mapped_column(Float)
    detector_confidence: Mapped[float] = mapped_column(Float)
    event_confidence: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lines.id", ondelete="SET NULL")
    )
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB)
    note: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    false_positive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    snapshot: Mapped["SnapshotModel | None"] = relationship(lazy="selectin", uselist=False)


class SnapshotModel(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        CheckConstraint("width > 0 AND height > 0 AND size_bytes > 0", name="dimensions"),
        CheckConstraint("content_type = 'image/jpeg'", name="content_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), unique=True
    )
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CameraSampleModel(Base):
    __tablename__ = "camera_samples"
    __table_args__ = (
        Index("ix_camera_samples_camera_time", "camera_id", "at"),
        Index("ix_camera_samples_at", "at"),
        CheckConstraint(
            "persons >= 0 AND persons_in_zone >= 0 AND observed_seconds >= 0", name="counts"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    persons: Mapped[int] = mapped_column(Integer)
    persons_in_zone: Mapped[int] = mapped_column(Integer)
    observed_seconds: Mapped[float] = mapped_column(Float)


class TrackSessionModel(Base):
    __tablename__ = "track_sessions"
    __table_args__ = (
        Index("ix_track_sessions_camera_time", "camera_id", "started_at"),
        Index("ix_track_sessions_ended_at", "ended_at"),
        CheckConstraint("ended_at >= started_at AND track_id > 0", name="ordered"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    track_id: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    segments: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    truncated: Mapped[bool] = mapped_column(Boolean, server_default="false")
