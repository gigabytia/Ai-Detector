"""One inference executor; latest-frame sampling, deadline batching and fair rotation."""

import asyncio
import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from uuid import UUID

from ai_detector_core.cameras.source import SourceType
from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraStatus
from vision_worker.cameras.frame import Frame
from vision_worker.cameras.manager import CameraManager
from vision_worker.cameras.scenario import load_scenario
from vision_worker.cameras.session import CameraSession
from vision_worker.inference.adapters.scripted import ScriptedPersonDetector
from vision_worker.inference.detector import PersonDetector
from vision_worker.pipeline.preview import PreviewHub
from vision_worker.pipeline.results import DetectionResult
from vision_worker.rules.registry import SceneRegistry
from vision_worker.tracking.registry import TrackerRegistry, TrackKey

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkItem:
    session: CameraSession
    frame: Frame
    confidence: float
    spec: CameraSpec | None = None


class InferenceScheduler:
    def __init__(
        self,
        manager: CameraManager,
        detector: PersonDetector,
        preview: PreviewHub,
        batch_size: int = 4,
        max_wait_ms: float = 20,
        trackers: TrackerRegistry | None = None,
        scenes: SceneRegistry | None = None,
    ) -> None:
        self._scenes = scenes if scenes is not None else SceneRegistry()
        self._trackers = trackers if trackers is not None else TrackerRegistry()
        self._manager = manager
        self._detector = detector
        self._preview = preview
        self._batch_size = batch_size
        self._max_wait = max_wait_ms / 1000
        self._order: deque[UUID] = deque()
        self._next_due: dict[UUID, float] = {}
        self._scripted: dict[str, ScriptedPersonDetector] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.healthy = True
        self._model_failures = 0

    def collect(self, limit: int, excluded: set[UUID] | None = None) -> list[WorkItem]:
        sessions = {s.camera_id: s for s in self._manager.sessions if isinstance(s, CameraSession)}
        self._order = deque(cid for cid in self._order if cid in sessions)
        known = set(self._order)
        self._order.extend(cid for cid in sessions if cid not in known)
        live_runs = {s.run_id for s in sessions.values()}
        self._next_due = {rid: due for rid, due in self._next_due.items() if rid in live_runs}
        items = []
        now = time.monotonic()
        for _ in range(len(self._order)):
            cid = self._order.popleft()
            self._order.append(cid)
            session = sessions[cid]
            session.check_performance()
            if excluded and cid in excluded:
                continue
            if session.state not in (CameraStatus.RUNNING, CameraStatus.DEGRADED):
                continue
            if now < self._next_due.get(session.run_id, 0):
                continue
            frame = session.buffer.take()
            if frame is None:
                continue
            self._next_due[session.run_id] = now + 1 / session.spec.config.target_fps
            items.append(
                WorkItem(session, frame, session.spec.config.detection_confidence, session.spec)
            )
            if len(items) == limit:
                break
        return items

    def _infer(self, items: list[WorkItem]) -> list[DetectionResult | Exception]:
        results: list[DetectionResult | Exception] = [RuntimeError("unprocessed frame")] * len(
            items
        )
        real = [
            i for i, item in enumerate(items) if item.session.spec.source_type != SourceType.MOCK
        ]
        if real:
            started = time.perf_counter()
            try:
                output = self._detector.detect(
                    [items[i].frame for i in real], min(items[i].confidence for i in real)
                )
                if len(output) != len(real):
                    raise ValueError("detector returned an invalid batch size")
                elapsed = (time.perf_counter() - started) * 1000 / len(real)
                for i, detections in zip(real, output, strict=True):
                    item = items[i]
                    results[i] = DetectionResult(
                        item.session.camera_id,
                        item.session.run_id,
                        item.frame,
                        tuple(d for d in detections if d.confidence >= item.confidence),
                        elapsed,
                    )
            except Exception as exc:
                logger.exception("inference batch failed")
                for i in real:
                    results[i] = exc
        for i, item in enumerate(items):
            if i in real:
                continue
            try:
                scenario = item.session.spec.source_url.removeprefix("mock://")
                if scenario not in self._scripted:
                    self._scripted[scenario] = ScriptedPersonDetector(load_scenario(scenario))
                started = time.perf_counter()
                detections = self._scripted[scenario].detect([item.frame], item.confidence)[0]
                results[i] = DetectionResult(
                    item.session.camera_id,
                    item.session.run_id,
                    item.frame,
                    tuple(detections),
                    (time.perf_counter() - started) * 1000,
                )
            except Exception as exc:
                logger.exception("scripted detection failed")
                results[i] = exc
        return results

    def _record_batch_health(
        self, items: list[WorkItem], results: list[DetectionResult | Exception]
    ) -> None:
        real = [
            result
            for item, result in zip(items, results, strict=True)
            if item.session.spec.source_type != SourceType.MOCK
        ]
        if real:
            self._model_failures = (
                self._model_failures + 1 if any(isinstance(r, Exception) for r in real) else 0
            )
            self.healthy = self._model_failures < 3

    def _process(self, items: list[WorkItem]) -> list[DetectionResult | Exception]:
        results = self._infer(items)
        self._record_batch_health(items, results)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            try:
                spec = items[i].spec
                if spec is None:
                    spec = items[i].session.spec
                tracked = replace(result, tracks=self._trackers.update(result), zones=spec.zones)
                results[i] = self._scenes.update(tracked, spec.config)
            except Exception as exc:
                logger.exception(
                    "person pipeline failed", extra={"camera_id": str(result.camera_id)}
                )
                results[i] = exc
        return results

    def _retain(self, active: set[TrackKey]) -> None:
        self._trackers.retain(active)
        self._scenes.retain(active)

    async def run(self, stop: asyncio.Event) -> None:
        active_keys: set[TrackKey] = set()
        try:
            while not stop.is_set():
                current = {
                    (s.camera_id, s.run_id)
                    for s in self._manager.sessions
                    if isinstance(s, CameraSession)
                    and s.state
                    in (
                        CameraStatus.RUNNING,
                        CameraStatus.DEGRADED,
                        CameraStatus.RECONNECTING,
                        CameraStatus.STARTING,
                    )
                }
                if current != active_keys:
                    await asyncio.get_running_loop().run_in_executor(
                        self._pool, self._retain, current
                    )
                    active_keys = current
                items = self.collect(self._batch_size)
                if not items:
                    await asyncio.sleep(0.005)
                    continue
                deadline = time.monotonic() + self._max_wait
                while (
                    len(items) < self._batch_size
                    and time.monotonic() < deadline
                    and not stop.is_set()
                ):
                    await asyncio.sleep(min(0.005, max(0, deadline - time.monotonic())))
                    items.extend(
                        self.collect(
                            self._batch_size - len(items), {i.session.camera_id for i in items}
                        )
                    )
                if stop.is_set():
                    break
                results = await asyncio.get_running_loop().run_in_executor(
                    self._pool, self._process, items
                )
                active = {s.run_id for s in self._manager.sessions if isinstance(s, CameraSession)}
                for item, result in zip(items, results, strict=True):
                    if item.session.run_id not in active or item.session.state not in (
                        CameraStatus.RUNNING,
                        CameraStatus.DEGRADED,
                    ):
                        continue  # restart/stop happened during inference: discard obsolete results
                    if isinstance(result, Exception):
                        item.session.record_inference_error(result)
                    else:
                        for event in result.events:
                            logger.info(
                                "person entered danger zone",
                                extra={
                                    "event_id": str(event.id),
                                    "event": event.model_dump(mode="json"),
                                    "event_type": event.type,
                                    "camera_id": str(event.camera_id),
                                    "run_id": str(event.run_id),
                                    "track_id": event.track_id,
                                    "zone_id": str(event.zone_id),
                                },
                            )
                        item.session.record_result(result)
                        self._preview.offer(result)
        except Exception:
            self.healthy = False
            raise
        finally:
            await asyncio.get_running_loop().run_in_executor(self._pool, self._retain, set())
            self._pool.shutdown(wait=True)
