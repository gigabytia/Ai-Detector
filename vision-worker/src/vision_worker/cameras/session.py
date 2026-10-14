"""CameraSession: runtime of one camera — source, capture thread, buffer, lifecycle (§29)."""

import logging
import threading
import time
import uuid
from datetime import datetime

from ai_detector_core.cameras.spec import CameraSpec
from ai_detector_core.cameras.status import CameraRuntimeStatus, CameraStatus
from ai_detector_core.ports.clock import Clock
from vision_worker.cameras.lifecycle import CameraLifecycle
from vision_worker.cameras.metrics import RateMeter
from vision_worker.cameras.reconnect import Backoff, BackoffPolicy
from vision_worker.cameras.source import FrameSource, SourceFatalError, SourceUnavailableError
from vision_worker.pipeline.frame_buffer import LatestFrameBuffer
from vision_worker.pipeline.results import DetectionResult

logger = logging.getLogger(__name__)

STOP_JOIN_TIMEOUT_SECONDS = 10.0


class CameraSession:
    def __init__(
        self,
        spec: CameraSpec,
        source: FrameSource,
        backoff: BackoffPolicy,
        worker_id: str,
        clock: Clock,
    ) -> None:
        self.spec = spec
        self.run_id = uuid.uuid4()
        self.buffer = LatestFrameBuffer()
        self._source = source
        self._backoff = Backoff(backoff)
        self._worker_id = worker_id
        self._clock = clock
        self._lifecycle = CameraLifecycle()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rate = RateMeter()
        self._processed_rate = RateMeter()
        self._result: DetectionResult | None = None
        self._inference_error: str | None = None
        self._low_fps_since: float | None = None
        self._lock = threading.Lock()
        self._frame_size: tuple[int, int] | None = None
        self._last_frame_at: datetime | None = None
        self._last_error: str | None = None
        self._last_reconnect_attempt_at: datetime | None = None

    @property
    def camera_id(self) -> uuid.UUID:
        return self.spec.id

    @property
    def state(self) -> CameraStatus:
        return self._lifecycle.state

    def record_result(self, result: DetectionResult) -> None:
        with self._lock:
            self._result = result
            self._processed_rate.tick()
            self._inference_error = None
        self.check_performance()

    def record_inference_error(self, error: Exception) -> None:
        with self._lock:
            self._inference_error = str(error) or type(error).__name__
        self._lifecycle.try_transition(CameraStatus.DEGRADED)

    def check_performance(self) -> None:
        if self.state not in (CameraStatus.RUNNING, CameraStatus.DEGRADED):
            return
        now = time.monotonic()
        with self._lock:
            target = min(
                self.spec.config.target_fps, self._rate.rate() or self.spec.config.target_fps
            )
            low = self._processed_rate.rate() < 0.8 * target
            if low:
                if self._low_fps_since is None:
                    self._low_fps_since = now
            else:
                self._low_fps_since = None
            degraded = self._inference_error is not None or (
                self._low_fps_since is not None and now - self._low_fps_since >= 5
            )
        self._lifecycle.try_transition(CameraStatus.DEGRADED if degraded else CameraStatus.RUNNING)

    def start(self) -> None:
        self._lifecycle.transition(CameraStatus.STARTING)
        self._thread = threading.Thread(
            target=self._capture_loop, name=f"capture-{self.camera_id}", daemon=True
        )
        self._thread.start()
        logger.info("camera starting", extra=self._log_extra())

    def stop(self) -> None:
        """Blocking: signals the capture thread and waits for it to release the source."""
        self._lifecycle.try_transition(CameraStatus.STOPPING)
        self._stop.set()
        self._source.stop()
        if self._thread is not None:
            self._thread.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)
            if self._thread.is_alive():
                logger.error("capture thread did not stop in time", extra=self._log_extra())
        self._lifecycle.try_transition(CameraStatus.STOPPED)
        logger.info("camera stopped", extra=self._log_extra())

    def status(self) -> CameraRuntimeStatus:
        with self._lock:
            return CameraRuntimeStatus(
                camera_id=self.camera_id,
                run_id=self.run_id,
                worker_id=self._worker_id,
                status=self._lifecycle.state,
                capture_fps=round(self._rate.rate(), 2),
                processed_fps=round(self._processed_rate.rate(), 2),
                inference_ms=round(self._result.inference_ms, 2) if self._result else None,
                detections_count=len(self._result.detections) if self._result else 0,
                dropped_frames=self.buffer.dropped,
                inference_error=self._inference_error,
                frame_size=self._frame_size,
                last_frame_at=self._last_frame_at,
                last_error=self._last_error,
                reconnect_attempts=self._backoff.attempts,
                last_reconnect_attempt_at=self._last_reconnect_attempt_at,
                updated_at=self._clock.now(),
            )

    def _capture_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    self._source.start()
                    self._read_frames()
                except SourceUnavailableError as exc:
                    if self._stop.is_set() or not self._wait_reconnect(exc):
                        break
                except SourceFatalError as exc:
                    self._fail(exc)
                    break
        except Exception as exc:
            logger.exception("camera capture crashed", extra=self._log_extra(exc))
            self._set_error(exc)
            self._lifecycle.try_transition(CameraStatus.ERROR)
        finally:
            self._source.close()

    def _read_frames(self) -> None:
        first = True
        while not self._stop.is_set() and (frame := self._source.read()) is not None:
            if first:
                first = False
                self._backoff.reset()
                if self._lifecycle.try_transition(CameraStatus.RUNNING):
                    logger.info("camera running", extra=self._log_extra())
            self.buffer.put(frame)
            with self._lock:
                self._rate.tick()
                self._frame_size = frame.size
                self._last_frame_at = frame.captured_at
                self._last_error = None

    def _wait_reconnect(self, exc: SourceUnavailableError) -> bool:
        logger.warning("camera source unavailable", extra=self._log_extra(exc), exc_info=exc)
        self._set_error(exc)
        self._source.close()
        if not self._lifecycle.try_transition(CameraStatus.RECONNECTING):
            return False
        delay = self._backoff.next_delay()
        with self._lock:
            self._last_reconnect_attempt_at = self._clock.now()
        if self._stop.wait(delay):
            return False
        return self._lifecycle.try_transition(CameraStatus.STARTING)

    def _fail(self, exc: SourceFatalError) -> None:
        logger.error("camera source failed", extra=self._log_extra(exc), exc_info=exc)
        self._set_error(exc)
        self._lifecycle.try_transition(CameraStatus.ERROR)

    def _set_error(self, exc: Exception) -> None:
        with self._lock:
            self._last_error = str(exc) or type(exc).__name__

    def _log_extra(self, exc: Exception | None = None) -> dict[str, object]:
        extra: dict[str, object] = {
            "camera_id": str(self.camera_id),
            "camera_name": self.spec.name,
            "run_id": str(self.run_id),
            "source": self._source.label,
        }
        if exc is not None:
            extra["error_type"] = type(exc).__name__
        return extra
