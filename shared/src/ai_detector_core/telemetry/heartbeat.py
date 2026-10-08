"""Worker heartbeat published to Redis and read by the API."""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class WorkerHeartbeat(BaseModel):
    model_config = ConfigDict(frozen=True)

    worker_id: str = Field(min_length=1, max_length=128)
    version: str
    started_at: AwareDatetime
    sent_at: AwareDatetime

    def uptime_seconds(self, now: datetime) -> float:
        return max(0.0, (now - self.started_at).total_seconds())
