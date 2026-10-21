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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

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
