import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.application.camera_service import CameraView
from app.infrastructure.database.models import CameraModel
from app.schemas.cameras import CameraCreate, CameraRead


def test_create_strips_name_and_validates_source() -> None:
    body = CameraCreate(name="  Вход  ", source_type="mock", source_url="mock://walk_through")
    assert body.name == "Вход"
    assert body.enabled is False
    with pytest.raises(ValidationError):
        CameraCreate(name="x", source_type="rtsp", source_url="mock://walk_through")
    with pytest.raises(ValidationError):
        CameraCreate(name="   ", source_type="mock", source_url="mock://walk_through")
    with pytest.raises(ValidationError):
        CameraCreate.model_validate(
            {"name": "x", "source_type": "mock", "source_url": "mock://a", "extra": 1}
        )


def test_read_masks_credentials() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    model = CameraModel(
        id=uuid.uuid4(),
        name="Вход",
        source_type="rtsp",
        source_url="rtsp://admin:secret@cam.local:554/s",
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    read = CameraRead.from_view(CameraView(camera=model, runtime=None))
    assert read.source_url == "rtsp://***:***@cam.local:554/s"
    assert read.runtime is None
