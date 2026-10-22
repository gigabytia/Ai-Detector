"""Lease-protected retention. Delete files before rows; never delete event history.

Orphans (e.g. worker crash between file write and Stream delivery) and abandoned
atomic-write temporary files use the same conservative age cutoff as metadata.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from itertools import islice
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_detector_core.storage.snapshots import LocalSnapshotStorage
from app.infrastructure.database.models import SnapshotModel

logger = logging.getLogger(__name__)
LOCK = "ad:snapshots:retention-lock"
RENEW = (
    "if redis.call('GET',KEYS[1]) == ARGV[1] then "
    "return redis.call('EXPIRE',KEYS[1],120) else return 0 end"
)
RELEASE = (
    "if redis.call('GET',KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL',KEYS[1]) else return 0 end"
)


class SnapshotRetention:
    def __init__(
        self,
        redis: Redis,
        sessions: async_sessionmaker[AsyncSession],
        storage: LocalSnapshotStorage,
        days: int = 30,
        interval: float = 3600,
    ) -> None:
        self.redis, self.sessions, self.storage = redis, sessions, storage
        self.days, self.interval = days, interval

    async def clean(self, cutoff: datetime) -> None:
        # Bound each transaction; failed file deletions stay retryable next pass.
        cursor = None
        while True:
            async with self.sessions() as session:
                query = select(SnapshotModel).where(SnapshotModel.created_at < cutoff)
                if cursor is not None:
                    query = query.where(SnapshotModel.id > cursor)
                rows = list(await session.scalars(query.order_by(SnapshotModel.id).limit(100)))
                if not rows:
                    break
                cursor = rows[-1].id
                for row in rows:
                    try:
                        await asyncio.to_thread(self.storage.delete, row.storage_key)
                    except (OSError, ValueError):
                        logger.exception(
                            "snapshot deletion deferred", extra={"snapshot_id": str(row.id)}
                        )
                        continue
                    await session.execute(delete(SnapshotModel).where(SnapshotModel.id == row.id))
                await session.commit()
        keys = self.storage.expired_keys(cutoff)
        while batch := await asyncio.to_thread(lambda: list(islice(keys, 100))):
            async with self.sessions() as session:
                referenced = set(
                    await session.scalars(
                        select(SnapshotModel.storage_key).where(
                            SnapshotModel.storage_key.in_(batch)
                        )
                    )
                )
            for key in batch:
                if key not in referenced:
                    try:
                        await asyncio.to_thread(self.storage.delete, key)
                    except (OSError, ValueError):
                        logger.exception("orphan snapshot deletion deferred")
        await asyncio.to_thread(self.storage.prune_temporary, cutoff)

    async def once(self) -> bool:
        token = str(uuid4())
        if not await self.redis.set(LOCK, token, nx=True, ex=120):
            return False
        job = asyncio.create_task(self.clean(datetime.now(UTC) - timedelta(days=self.days)))
        try:
            while not job.done():
                done, _ = await asyncio.wait({job}, timeout=30)
                if not done and not await self.redis.eval(RENEW, 1, LOCK, token):
                    raise RuntimeError("snapshot retention lease lost")
            await job
            return True
        finally:
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
            with contextlib.suppress(RedisError):
                await self.redis.eval(RELEASE, 1, LOCK, token)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.once()
            except (RedisError, SQLAlchemyError, OSError, RuntimeError):
                logger.exception("snapshot retention deferred")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.interval)
