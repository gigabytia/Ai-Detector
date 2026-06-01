from typing import List, Optional, Tuple

def point_in_poly(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

def line_side(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

def has_crossed(prev_side: Optional[float], cur_side: float) -> bool:
    if prev_side is None:
        return False
    if prev_side == 0:
        return False
    return (prev_side > 0) != (cur_side > 0)