"""At-least-once consumer. Commit before ACK; reclaim orphaned pending entries.

Never MAXLEN-trim unpersisted input. Committed entries are ACKed and deleted.
Poison input is copied to a bounded dead stream before ACK in one transaction.
"""

import asyncio
import contextlib
import logging
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_detector_core.events.domain import DomainEvent
from ai_detector_core.telemetry.event_bus import (
    DEAD_STREAM,
    INGEST_GROUP,
    INGEST_STREAM,
    pending_event_key,
)
from app.infrastructure.database.models import CameraModel, EventModel, ZoneModel

logger = logging.getLogger(__name__)


def stream_messages(result: object) -> list[tuple[bytes, dict[bytes, bytes]]]:
    # redis-py exposes RESP2/RESP3 union types; this client uses default RESP2/bytes.
    streams = cast(list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]], result)
    return streams[0][1] if streams else []


class EventIngest:
    def __init__(self, redis: Redis, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.redis = redis
        self.sessions = sessions
        self.consumer = f"api-{uuid4()}"

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(INGEST_STREAM, INGEST_GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def process(self, messages: list[tuple[bytes, dict[bytes, bytes]]]) -> None:
        persisted: list[UUID] = []
        valid: list[tuple[bytes, DomainEvent]] = []
        dead: list[tuple[bytes, dict[bytes, bytes], str]] = []
        for message_id, fields in messages:
            try:
                raw = fields[b"event"]
                if len(raw) > 65536:
                    raise ValueError("event exceeds 64 KiB")
                valid.append((message_id, DomainEvent.model_validate_json(raw)))
            except (KeyError, ValidationError, ValueError) as exc:
                dead.append((message_id, fields, type(exc).__name__))
        async with self.sessions() as session, session.begin():
            if valid:
                camera_ids = {event.camera_id for _, event in valid}
                cameras = set(
                    await session.scalars(
                        select(CameraModel.id).where(CameraModel.id.in_(camera_ids))
                    )
                )
                zone_ids = {event.zone_id for _, event in valid}
                # Hold key-share locks so concurrent zone delete cannot race the FK insert.
                zones = dict(
                    (
                        await session.execute(
                            select(ZoneModel.id, ZoneModel.camera_id)
                            .where(ZoneModel.id.in_(zone_ids))
                            .with_for_update(read=True, key_share=True)
                        )
                    ).all()
                )
                rows = []
                for message_id, event in valid:
                    if event.camera_id not in cameras:
                        dead.append(
                            (
                                message_id,
                                {b"event": event.model_dump_json().encode()},
                                "unknown camera",
                            )
                        )
                        continue
                    row = event.model_dump()
                    row["zone_id"] = (
                        event.zone_id if zones.get(event.zone_id) == event.camera_id else None
                    )
                    row["metadata"] = event.metadata.model_dump(mode="json")
                    rows.append(row)
                    persisted.append(event.id)
                if rows:
                    await session.execute(
                        insert(cast(Table, EventModel.__table__))
                        .values(rows)
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
        # DB commit succeeded. Lost ACK causes retry, UUID prevents another insert.
        async with self.redis.pipeline(transaction=True) as pipe:
            for message_id, fields, reason in dead:
                pipe.xadd(
                    DEAD_STREAM,
                    {
                        "message_id": message_id,
                        "reason": reason,
                        "payload": repr(fields)[:65536],
                    },
                    maxlen=1000,
                    approximate=True,
                )
                logger.warning(
                    "invalid ingest message",
                    extra={"message_id": str(message_id), "reason": reason},
                )
            for event_id in persisted:
                pipe.delete(pending_event_key(event_id))
            ids = [message_id for message_id, _ in messages]
            if ids:
                pipe.xack(INGEST_STREAM, INGEST_GROUP, *ids)
                pipe.xdel(INGEST_STREAM, *ids)
            await pipe.execute()

    async def run(self, stop: asyncio.Event) -> None:
        delay = 0.25
        claim_cursor = "0-0"
        while not stop.is_set():
            try:
                await self.ensure_group()
                # Retry our failed batch first, then recover a crashed API consumer.
                result = await self.redis.xreadgroup(
                    INGEST_GROUP,
                    self.consumer,
                    {INGEST_STREAM: "0"},
                    count=200,
                )
                messages = stream_messages(result)
                if not messages:
                    claimed = await self.redis.xautoclaim(
                        INGEST_STREAM,
                        INGEST_GROUP,
                        self.consumer,
                        min_idle_time=30000,
                        start_id=claim_cursor,
                        count=200,
                    )
                    claim_cursor = claimed[0]
                    messages = cast(list[tuple[bytes, dict[bytes, bytes]]], claimed[1])
                if not messages:
                    result = await self.redis.xreadgroup(
                        INGEST_GROUP,
                        self.consumer,
                        {INGEST_STREAM: ">"},
                        count=200,
                        block=500,
                    )
                    messages = stream_messages(result)
                if messages:
                    await self.process(messages)
                delay = 0.25
            except (RedisError, SQLAlchemyError, OSError):
                logger.exception("event ingest delayed; batch remains pending")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                delay = min(delay * 2, 5)
