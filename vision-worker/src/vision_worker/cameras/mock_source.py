"""Synthetic frames drawn from a scenario (ADR-016). Detections come from the same scenario."""

import threading
from datetime import UTC, datetime

import cv2
import numpy as np

from vision_worker.cameras.frame import Frame, Image
from vision_worker.cameras.pacing import RealtimePacer
from vision_worker.cameras.scenario import Scenario, UnknownScenarioError, load_scenario
from vision_worker.cameras.source import SourceFatalError

PERSON_COLOR = (60, 70, 160)
HEAD_COLOR = (120, 140, 200)


def render_scene(background: Image, scenario: Scenario, t: float) -> Image:
    """Draw people at scenario time t onto a copy of the background."""
    image = background.copy()
    width, height = scenario.width, scenario.height
    for _, (x1, y1, x2, y2) in scenario.boxes_at(t):
        p1 = (int(x1 * width), int(y1 * height) + int((y2 - y1) * height * 0.18))
        p2 = (int(x2 * width), int(y2 * height))
        cv2.rectangle(image, p1, p2, PERSON_COLOR, thickness=-1)
        head_center = (int((x1 + x2) / 2 * width), int(y1 * height + (y2 - y1) * height * 0.09))
        cv2.circle(image, head_center, max(2, int((y2 - y1) * height * 0.09)), HEAD_COLOR, -1)
    return image


def make_background(width: int, height: int) -> Image:
    gradient = np.linspace(170, 120, height, dtype=np.uint8)[:, None]
    gray = np.repeat(gradient, width, axis=1)
    return np.dstack([gray, gray, gray]).astype(np.uint8)


class MockFrameSource:
    def __init__(self, scenario_name: str) -> None:
        self._scenario_name = scenario_name
        self._scenario: Scenario | None = None
        self._background: Image | None = None
        self._stop = threading.Event()
        self._pacer = RealtimePacer(self._stop)
        self._next_frame_id = 0
        self._loop_index = 0

    @property
    def label(self) -> str:
        return f"mock:{self._scenario_name}"

    @property
    def scenario(self) -> Scenario | None:
        return self._scenario

    def start(self) -> None:
        try:
            self._scenario = load_scenario(self._scenario_name)
        except UnknownScenarioError as exc:
            raise SourceFatalError(f"unknown mock scenario: {self._scenario_name}") from exc
        self._background = make_background(self._scenario.width, self._scenario.height)
        self._pacer.reset()
        self._next_frame_id = 0
        self._loop_index = 0

    def read(self) -> Frame | None:
        scenario, background = self._scenario, self._background
        if scenario is None or background is None:
            return None
        source_ts_ms = self._next_frame_id * 1000.0 / scenario.fps
        if not self._pacer.wait_until(source_ts_ms):
            return None
        t = source_ts_ms / 1000.0
        loop_index = int(t // scenario.duration_s)
        discontinuity, self._loop_index = loop_index != self._loop_index, loop_index
        self._next_frame_id += 1
        return Frame(
            image=render_scene(background, scenario, t),
            frame_id=self._next_frame_id,
            source_ts_ms=source_ts_ms,
            captured_at=datetime.now(UTC),
            discontinuity=discontinuity,
        )

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self._background = None
