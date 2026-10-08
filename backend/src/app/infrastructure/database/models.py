"""SQLAlchemy models. Schema documentation: docs/database.md."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
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
