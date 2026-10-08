"""Scripted scenes for mock cameras and deterministic tests (ADR-016).

People move linearly between keyframes; outside their keyframe range they are absent.
"""

from importlib import resources
from itertools import pairwise
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NormalizedBox = tuple[
    Annotated[float, Field(ge=0, le=1)],
    Annotated[float, Field(ge=0, le=1)],
    Annotated[float, Field(ge=0, le=1)],
    Annotated[float, Field(ge=0, le=1)],
]


class Keyframe(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: float = Field(ge=0, description="seconds from scenario start")
    bbox: NormalizedBox

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        x1, y1, x2, y2 = self.bbox
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must be (x1, y1, x2, y2) with x2 > x1 and y2 > y1")
        return self


class ScriptedPerson(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    keyframes: list[Keyframe] = Field(min_length=2)

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        times = [k.t for k in self.keyframes]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("keyframes must have strictly increasing t")
        return self

    def bbox_at(self, t: float) -> NormalizedBox | None:
        frames = self.keyframes
        if t < frames[0].t or t > frames[-1].t:
            return None
        for start, end in pairwise(frames):
            if start.t <= t <= end.t:
                k = (t - start.t) / (end.t - start.t)
                a, b = start.bbox, end.bbox
                return (
                    a[0] + (b[0] - a[0]) * k,
                    a[1] + (b[1] - a[1]) * k,
                    a[2] + (b[2] - a[2]) * k,
                    a[3] + (b[3] - a[3]) * k,
                )
        return None


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    width: int = Field(ge=64, le=3840)
    height: int = Field(ge=64, le=2160)
    fps: float = Field(gt=0, le=60)
    duration_s: float = Field(gt=0)
    people: list[ScriptedPerson]

    def boxes_at(self, t: float) -> list[tuple[int, NormalizedBox]]:
        local_t = t % self.duration_s
        boxes = [(p.id, p.bbox_at(local_t)) for p in self.people]
        return [(pid, box) for pid, box in boxes if box is not None]


class UnknownScenarioError(LookupError):
    pass


def load_scenario(name: str) -> Scenario:
    """Load a bundled scenario from vision_worker/scenarios/<name>.json."""
    path = resources.files("vision_worker.scenarios").joinpath(f"{name}.json")
    if not path.is_file():
        raise UnknownScenarioError(name)
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))
