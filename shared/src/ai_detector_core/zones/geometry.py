"""Small deterministic geometry in normalized coordinates; boundaries are inside."""

from collections.abc import Sequence

Point = tuple[float, float]
EPSILON = 1e-9


def cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(p: Point, a: Point, b: Point) -> bool:
    return (
        abs(cross(a, b, p)) <= EPSILON
        and min(a[0], b[0]) - EPSILON <= p[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= p[1] <= max(a[1], b[1]) + EPSILON
    )


def intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    values = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return (values[0] * values[1] < 0 and values[2] * values[3] < 0) or any(
        (on_segment(c, a, b), on_segment(d, a, b), on_segment(a, c, d), on_segment(b, c, d))
    )


def validate_polygon(points: Sequence[Point]) -> None:
    if not 3 <= len(points) <= 64 or len(set(points)) != len(points):
        raise ValueError("polygon requires 3..64 distinct vertices; closing vertex is implicit")
    edges = list(zip(points, (*points[1:], points[0]), strict=True))
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)
    if abs(area) <= EPSILON:
        raise ValueError("polygon area must be positive")
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i or j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if intersects(a, b, c, d):
                raise ValueError("polygon must not self-intersect or touch itself")
    # Adjacent edges cannot fold back over each other either.
    for i, p in enumerate(points):
        a, b = points[i - 1], points[(i + 1) % len(points)]
        if on_segment(b, a, p) or on_segment(a, p, b):
            raise ValueError("adjacent polygon edges must not overlap")


def point_in_polygon(point: Point, points: Sequence[Point]) -> bool:
    inside = False
    for a, b in zip(points, (*points[1:], points[0]), strict=True):
        if on_segment(point, a, b):
            return True
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                inside = not inside
    return inside
