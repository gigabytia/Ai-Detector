"""Redis key and channel names. Both services import them from here to stay in sync."""

KEY_PREFIX = "ad"

# Heartbeat keys expire on their own, so a crashed worker disappears without cleanup.
WORKER_HEARTBEAT_TTL_SECONDS = 5
WORKER_HEARTBEAT_PATTERN = f"{KEY_PREFIX}:worker:*:heartbeat"


def worker_heartbeat_key(worker_id: str) -> str:
    return f"{KEY_PREFIX}:worker:{worker_id}:heartbeat"
