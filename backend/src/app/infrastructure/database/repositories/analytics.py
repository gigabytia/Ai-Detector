"""Bounded database aggregations; never fetch every event/frame into Python."""

import base64
import json
import math
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_detector_core.telemetry.analytics import TrackSession
from app.application.event_service import decode_cursor
from app.infrastructure.database.models import (
    CameraModel,
    CameraSampleModel,
    EventModel,
    TrackSessionModel,
)
from app.schemas.analytics import (
    CameraStatistics,
    Dashboard,
    EventCount,
    PeopleBucket,
    TimeBucket,
    TrackPage,
)


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard(
        self, start: datetime, end: datetime, camera_id: UUID | None, now: datetime
    ) -> Dashboard:
        # One MVCC snapshot across KPI/chart queries, even during concurrent ingest/status PATCH.
        await self.session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        cameras = list(
            await self.session.scalars(
                select(CameraModel)
                .where(*([CameraModel.id == camera_id] if camera_id else []))
                .order_by(CameraModel.name, CameraModel.id)
            )
        )
        ef = [EventModel.occurred_at >= start, EventModel.occurred_at < end]
        sf = [CameraSampleModel.at >= start, CameraSampleModel.at < end]
        tf = [TrackSessionModel.started_at < end, TrackSessionModel.ended_at >= start]
        if camera_id:
            ef.append(EventModel.camera_id == camera_id)
            sf.append(CameraSampleModel.camera_id == camera_id)
            tf.append(TrackSessionModel.camera_id == camera_id)
        summary = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count().filter(EventModel.severity == "critical"),
                    func.count().filter(EventModel.status == "FALSE_POSITIVE"),
                ).where(*ef)
            )
        ).one()
        per_camera = dict(
            (
                await self.session.execute(
                    select(EventModel.camera_id, func.count())
                    .where(*ef)
                    .group_by(EventModel.camera_id)
                )
            ).all()
        )
        per_type = (
            await self.session.execute(
                select(EventModel.type, func.count())
                .where(*ef)
                .group_by(EventModel.type)
                .order_by(EventModel.type)
            )
        ).all()
        samples = {
            row[0]: row
            for row in (
                await self.session.execute(
                    select(
                        CameraSampleModel.camera_id,
                        func.sum(CameraSampleModel.observed_seconds),
                        func.avg(CameraSampleModel.persons),
                        func.max(CameraSampleModel.persons),
                    )
                    .where(*sf)
                    .group_by(CameraSampleModel.camera_id)
                )
            ).all()
        }
        tracks = dict(
            (
                await self.session.execute(
                    select(TrackSessionModel.camera_id, func.count())
                    .where(*tf)
                    .group_by(TrackSessionModel.camera_id)
                )
            ).all()
        )
        seconds = max(1, math.ceil((end - start).total_seconds() / 120))
        event_bin = func.date_bin(timedelta(seconds=seconds), EventModel.occurred_at, start)
        counts: dict[datetime, int] = dict(
            (
                await self.session.execute(
                    select(event_bin, func.count()).where(*ef).group_by(event_bin)
                )
            ).all()
        )
        timeline = [
            TimeBucket(
                at=start + timedelta(seconds=i * seconds),
                events=int(counts.get(start + timedelta(seconds=i * seconds), 0)),
            )
            for i in range(math.ceil((end - start).total_seconds() / seconds))
        ]
        people = []
        # Occupancy is meaningful for ONE camera, never sum asynchronous camera observations.
        if camera_id:
            sample_bin = func.date_bin(timedelta(seconds=seconds), CameraSampleModel.at, start)
            rows = (
                await self.session.execute(
                    select(
                        sample_bin,
                        func.avg(CameraSampleModel.persons),
                        func.avg(CameraSampleModel.persons_in_zone),
                        func.count(),
                    )
                    .where(*sf)
                    .group_by(sample_bin)
                    .order_by(sample_bin)
                )
            ).all()
            people = [
                PeopleBucket(
                    at=row[0],
                    persons=float(row[1]),
                    persons_in_zone=float(row[2]),
                    samples=int(row[3]),
                )
                for row in rows
            ]
        return Dashboard(
            generated_at=now,
            start=start,
            end=end,
            camera_id=camera_id,
            total_events=int(summary[0]),
            critical_events=int(summary[1]),
            false_positives=int(summary[2]),
            enabled_cameras=sum(c.enabled and c.deleted_at is None for c in cameras),
            average_events_per_camera=int(summary[0]) / len(cameras) if cameras else None,
            completed_tracks=sum(int(n) for n in tracks.values()),
            by_type=[EventCount(key=str(k), count=int(n)) for k, n in per_type],
            by_camera=[
                CameraStatistics(
                    camera_id=c.id,
                    name=c.name,
                    archived=c.deleted_at is not None,
                    enabled=c.enabled and c.deleted_at is None,
                    events=int(per_camera.get(c.id, 0)),
                    observed_seconds=float(samples[c.id][1]) if c.id in samples else 0,
                    average_persons=float(samples[c.id][2]) if c.id in samples else None,
                    max_persons=int(samples[c.id][3]) if c.id in samples else None,
                    completed_tracks=int(tracks.get(c.id, 0)),
                )
                for c in cameras
            ],
            events_over_time=timeline,
            people_over_time=people,
            bucket_seconds=seconds,
        )

    async def tracks(
        self, start: datetime, end: datetime, camera_id: UUID | None, limit: int, cursor: str | None
    ) -> TrackPage:
        before = decode_cursor(cursor)
        query = select(TrackSessionModel).where(
            TrackSessionModel.started_at < end, TrackSessionModel.ended_at >= start
        )
        if camera_id:
            query = query.where(TrackSessionModel.camera_id == camera_id)
        if before:
            from sqlalchemy import tuple_

            query = query.where(tuple_(TrackSessionModel.ended_at, TrackSessionModel.id) < before)
        rows = list(
            await self.session.scalars(
                query.order_by(
                    TrackSessionModel.ended_at.desc(), TrackSessionModel.id.desc()
                ).limit(limit + 1)
            )
        )
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([last.ended_at.isoformat(), str(last.id)]).encode()
            ).decode()
        items = [
            TrackSession(
                id=row.id,
                camera_id=row.camera_id,
                run_id=row.run_id,
                track_id=row.track_id,
                started_at=row.started_at,
                ended_at=row.ended_at,
                segments=row.segments,
                truncated=row.truncated,
            )
            for row in rows[:limit]
        ]
        return TrackPage(items=items, next_cursor=next_cursor)
