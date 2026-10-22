"""Shared event transport names. Durable ingest is independent of live delivery."""

INGEST_STREAM = "ad:ingest"
INGEST_GROUP = "api-ingest"
DEAD_STREAM = "ad:ingest:dead"
EVENTS_LIVE = "ad:events:live"
EVENTS_UPDATES = "ad:events:updates"
CAMERAS_STATUS = "ad:cameras:status"


def pending_event_key(event_id: object) -> str:
    return f"ad:event:{event_id}:published"
