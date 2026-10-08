"""Redis key and channel names. Both services import them from here to stay in sync."""

from uuid import UUID

KEY_PREFIX = "ad"

# Status keys expire on their own, so a crashed worker disappears without cleanup.
WORKER_HEARTBEAT_TTL_SECONDS = 5
WORKER_HEARTBEAT_PATTERN = f"{KEY_PREFIX}:worker:*:heartbeat"
CAMERA_STATUS_TTL_SECONDS = 5

WORKER_COMMANDS_CHANNEL = f"{KEY_PREFIX}:worker:commands"


def worker_heartbeat_key(worker_id: str) -> str:
    return f"{KEY_PREFIX}:worker:{worker_id}:heartbeat"


def camera_status_key(camera_id: UUID) -> str:
    return f"{KEY_PREFIX}:camera:{camera_id}:status"
