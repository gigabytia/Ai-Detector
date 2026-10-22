"""Per-run membership state machines with source-time dwell and wall-clock cooldown."""

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from ai_detector_core.cameras.config import CameraConfig
from ai_detector_core.events.domain import DomainEvent, LoiteringMetadata, ZoneEntryMetadata
from ai_detector_core.people.track import PersonState, PersonTrack
from ai_detector_core.ports.clock import Clock
from ai_detector_core.zones.geometry import point_in_polygon
from ai_detector_core.zones.model import ZoneSpec
from vision_worker.cameras.frame import Frame

logger = logging.getLogger(__name__)


class Membership(StrEnum):
    OUTSIDE = "OUTSIDE"
    ENTERING = "ENTERING"
    INSIDE = "INSIDE"
    EXITING = "EXITING"


@dataclass
class Visit:
    phase: Membership = Membership.OUTSIDE
    elapsed: float = 0
    last_ts: float | None = None
    was_lost: bool = False
    confidence_sum: float = 0
    matches: int = 0
    frames: int = 0
    loiter_since: float | None = None
    loiter_elapsed: float = 0
    loiter_fired: bool = False


class ZoneEngine:
    def __init__(
        self,
        clock: Clock,
        min_hits: int = 3,
        severity: Literal["critical", "warning", "info"] = "critical",
        loitering_severity: Literal["critical", "warning", "info"] = "warning",
    ) -> None:
        self._clock = clock
        self._min_hits = min_hits
        self._severity = severity
        self._loitering_severity = loitering_severity
        self._loiter_cooldown: dict[int, datetime] = {}
        self._zones: dict[UUID, ZoneSpec] = {}
        self._visits: dict[tuple[int, UUID], Visit] = {}
        self._cooldown: dict[int, datetime] = {}

    def update(
        self,
        frame: Frame,
        tracks: tuple[PersonTrack, ...],
        zones: tuple[ZoneSpec, ...],
        config: CameraConfig,
    ) -> tuple[tuple[PersonTrack, ...], tuple[DomainEvent, ...]]:
        enabled = {z.id: z for z in zones if z.enabled}
        changed = {
            zid
            for zid, old in self._zones.items()
            if zid not in enabled or old.points != enabled[zid].points
        }
        active = {t.track_id for t in tracks}
        self._visits = {
            k: v for k, v in self._visits.items() if k[0] in active and k[1] not in changed
        }
        self._cooldown = {k: v for k, v in self._cooldown.items() if k in active}
        self._loiter_cooldown = {k: v for k, v in self._loiter_cooldown.items() if k in active}
        self._zones = dict(enabled)
        output, events = [], []
        width, height = frame.size
        for track in tracks:
            danger = False
            for zone in enabled.values():
                visit = self._visits.setdefault((track.track_id, zone.id), Visit())
                delta = (
                    0.0
                    if visit.last_ts is None or visit.was_lost
                    else max(0, (frame.source_ts_ms - visit.last_ts) / 1000)
                )
                raw_delta = (
                    None if visit.last_ts is None else (frame.source_ts_ms - visit.last_ts) / 1000
                )
                if raw_delta is not None and (raw_delta < 0 or raw_delta > 2):
                    visit.loiter_since = None
                    visit.loiter_elapsed = 0
                visit.last_ts = frame.source_ts_ms
                if track.state == PersonState.LOST:
                    visit.was_lost = True
                    visit.loiter_since = None
                    visit.loiter_elapsed = 0
                    if visit.phase == Membership.ENTERING:
                        visit.frames += 1
                    continue
                visit.was_lost = False
                anchor = track.anchor[0] / width, track.anchor[1] / height
                inside = point_in_polygon(anchor, tuple((p.x, p.y) for p in zone.points))
                if inside:
                    # Only consecutive observed-inside time counts. Entry dwell is part of it.
                    if visit.loiter_since is None:
                        visit.loiter_since = frame.source_ts_ms
                    visit.loiter_elapsed = (frame.source_ts_ms - visit.loiter_since) / 1000
                    if visit.phase == Membership.OUTSIDE:
                        visit.phase = Membership.ENTERING
                        visit.elapsed = visit.confidence_sum = 0
                        visit.matches = visit.frames = 0
                    elif visit.phase == Membership.EXITING:
                        visit.phase = Membership.INSIDE
                        visit.elapsed = 0
                    elif visit.phase == Membership.ENTERING:
                        visit.elapsed += delta
                    if visit.phase == Membership.ENTERING:
                        visit.confidence_sum += track.confidence
                        visit.matches += 1
                        visit.frames += 1
                        if (
                            visit.elapsed + 1e-9 >= config.zone_enter_dwell_seconds
                            and track.hits >= self._min_hits
                        ):
                            visit.phase = Membership.INSIDE
                            now = self._clock.now()
                            previous = self._cooldown.get(track.track_id)
                            if (
                                previous is None
                                or (now - previous).total_seconds() >= config.event_cooldown_seconds
                            ):
                                self._cooldown[track.track_id] = now
                                mean = visit.confidence_sum / visit.matches
                                stability = visit.matches / visit.frames
                                x1, y1, x2, y2 = track.bbox
                                events.append(
                                    DomainEvent(
                                        camera_id=track.camera_id,
                                        run_id=track.run_id,
                                        track_id=track.track_id,
                                        zone_id=zone.id,
                                        severity=self._severity,
                                        occurred_at=frame.captured_at,
                                        source_ts_ms=frame.source_ts_ms,
                                        detector_confidence=mean,
                                        event_confidence=mean * stability,
                                        message=(
                                            f"Человек #{track.track_id} вошёл "
                                            f"в опасную зону «{zone.name}»"
                                        ),
                                        metadata=ZoneEntryMetadata(
                                            bbox=(x1 / width, y1 / height, x2 / width, y2 / height),
                                            anchor=anchor,
                                            dwell_seconds=visit.elapsed,
                                            stability=stability,
                                        ),
                                    )
                                )
                            else:
                                logger.debug(
                                    "zone entry suppressed by cooldown",
                                    extra={
                                        "camera_id": str(track.camera_id),
                                        "run_id": str(track.run_id),
                                        "track_id": track.track_id,
                                        "zone_id": str(zone.id),
                                    },
                                )
                elif visit.phase == Membership.ENTERING:
                    visit.phase = Membership.OUTSIDE
                elif visit.phase == Membership.INSIDE:
                    visit.phase, visit.elapsed = Membership.EXITING, 0
                elif visit.phase == Membership.EXITING:
                    visit.elapsed += delta
                if not inside:
                    visit.loiter_since = None
                    visit.loiter_elapsed = 0
                if (
                    not inside
                    and visit.phase == Membership.EXITING
                    and visit.elapsed + 1e-9 >= config.zone_exit_grace_seconds
                ):
                    visit.phase = Membership.OUTSIDE
                    visit.loiter_fired = False
                if (
                    inside
                    and visit.phase == Membership.INSIDE
                    and not visit.loiter_fired
                    and visit.loiter_elapsed > config.loitering_threshold_seconds
                ):
                    # At most one attempt per confirmed visit; cooldown is type/track scoped.
                    visit.loiter_fired = True
                    now = self._clock.now()
                    previous = self._loiter_cooldown.get(track.track_id)
                    if (
                        previous is None
                        or (now - previous).total_seconds() >= config.event_cooldown_seconds
                    ):
                        self._loiter_cooldown[track.track_id] = now
                        x1, y1, x2, y2 = track.bbox
                        events.append(
                            DomainEvent(
                                camera_id=track.camera_id,
                                run_id=track.run_id,
                                track_id=track.track_id,
                                zone_id=zone.id,
                                type="PERSON_LOITERING_IN_DANGER_ZONE",
                                severity=self._loitering_severity,
                                occurred_at=frame.captured_at,
                                source_ts_ms=frame.source_ts_ms,
                                detector_confidence=track.confidence,
                                event_confidence=track.confidence,
                                message=(
                                    f"Человек #{track.track_id} долго находится "
                                    f"в опасной зоне «{zone.name}»"
                                ),
                                metadata=LoiteringMetadata(
                                    bbox=(x1 / width, y1 / height, x2 / width, y2 / height),
                                    anchor=anchor,
                                    stability=1,
                                    zone_name=zone.name,
                                    duration_seconds=visit.loiter_elapsed,
                                    threshold_seconds=config.loitering_threshold_seconds,
                                ),
                            )
                        )
                danger |= visit.phase in (Membership.INSIDE, Membership.EXITING)
            output.append(
                track
                if track.state == PersonState.LOST
                else replace(
                    track, state=PersonState.IN_DANGER_ZONE if danger else PersonState.NORMAL
                )
            )
        return tuple(output), tuple(events)
