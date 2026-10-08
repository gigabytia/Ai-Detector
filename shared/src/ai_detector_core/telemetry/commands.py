"""Commands from API to workers. They are notifications: the desired state lives in PostgreSQL."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkerCommandType(StrEnum):
    CAMERA_CHANGED = "camera.changed"  # re-read the camera spec and reconcile
    CAMERA_RESTART = "camera.restart"  # recreate the session (new run_id)


class WorkerCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: WorkerCommandType
    camera_id: UUID
