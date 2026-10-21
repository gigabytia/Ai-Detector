"""Normalized polygon validation, including concavity and boundary semantics."""

import pytest
from pydantic import ValidationError

from ai_detector_core.zones.geometry import point_in_polygon
from ai_detector_core.zones.model import ZoneShape

SQUARE = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))


@pytest.mark.parametrize(
    "point, expected",
    [
        ((0.5, 0.5), True),
        ((0.1, 0.5), True),
        ((0.1, 0.1), True),
        ((0, 0.5), False),
        ((1, 1), False),
    ],
)
def test_polygon_boundary_is_inside(point: tuple[float, float], expected: bool) -> None:
    assert point_in_polygon(point, SQUARE) == expected
    assert point_in_polygon(point, tuple(reversed(SQUARE))) == expected


def test_concave_polygon_and_notch() -> None:
    polygon = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 0.5), (0.0, 1.0))
    assert point_in_polygon((0.5, 0.2), polygon)
    assert not point_in_polygon((0.5, 0.9), polygon)
    ZoneShape(name="Concave", points=[{"x": x, "y": y} for x, y in polygon])


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (1, 1)],
        [(0, 0), (0.5, 0.5), (1, 1)],
        [(0, 0), (1, 1), (0, 1), (1, 0)],
        [(0, 0), (1, 0), (1, 1), (0, 0)],
        [(-0.1, 0), (1, 0), (1, 1)],
        [(0, 0), (1.1, 0), (1, 1)],
        [(float("nan"), 0), (1, 0), (1, 1)],
        [(0, 0), (1, 0), (0.5, 0), (1, 1), (0, 1)],
    ],
)
def test_invalid_polygons_are_rejected(points: list[tuple[float, float]]) -> None:
    with pytest.raises(ValidationError):
        ZoneShape(name="bad", points=[{"x": x, "y": y} for x, y in points])


def test_bounds_name_and_vertex_limit() -> None:
    with pytest.raises(ValidationError):
        ZoneShape(name="   ", points=[{"x": x, "y": y} for x, y in SQUARE])
    with pytest.raises(ValidationError):
        ZoneShape(name="big", points=[{"x": i / 65, "y": 0} for i in range(65)])
