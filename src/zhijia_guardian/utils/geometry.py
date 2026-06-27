from __future__ import annotations

import math
from typing import Sequence


Point2D = tuple[float, float]


def yaw_from_quaternion_wxyz(quat: Sequence[float]) -> float:
    """Return yaw from a quaternion in [w, x, y, z] order."""
    if len(quat) != 4:
        return 0.0
    w, x, y, z = [float(v) for v in quat]
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def yaw_from_quaternion_xyzw(qx: float, qy: float, qz: float, qw: float) -> float:
    return yaw_from_quaternion_wxyz([qw, qx, qy, qz])


def token_hex(token: bytes | memoryview | str | None) -> str | None:
    if token is None:
        return None
    if isinstance(token, str):
        return token
    if isinstance(token, memoryview):
        token = token.tobytes()
    return token.hex()


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x1 - x2, y1 - y2)


def point_to_actor_margin(
    point_x: float,
    point_y: float,
    actor_x: float,
    actor_y: float,
    actor_length: float,
    actor_width: float,
    ego_radius: float = 2.4,
) -> float:
    actor_radius = max(actor_length, actor_width, 1.0) / 2.0
    return euclidean_distance(point_x, point_y, actor_x, actor_y) - actor_radius - ego_radius


def oriented_box_margin(
    ego_x: float,
    ego_y: float,
    ego_yaw: float,
    actor_x: float,
    actor_y: float,
    actor_yaw: float,
    actor_length: float,
    actor_width: float,
    ego_length: float = 4.8,
    ego_width: float = 1.9,
) -> float:
    """Return signed rectangle separation: positive is clear, zero/negative overlaps."""
    ego = _rectangle_corners(ego_x, ego_y, ego_yaw, ego_length, ego_width)
    actor = _rectangle_corners(actor_x, actor_y, actor_yaw, actor_length, actor_width)
    axis_gaps = [_projection_gap(ego, actor, axis) for axis in _rectangle_axes(ego, actor)]
    if all(gap <= 0.0 for gap in axis_gaps):
        return max(axis_gaps)
    return min(
        _segment_distance(a1, a2, b1, b2)
        for a1, a2 in _edges(ego)
        for b1, b2 in _edges(actor)
    )


def _rectangle_corners(
    center_x: float,
    center_y: float,
    yaw: float,
    length: float,
    width: float,
) -> list[Point2D]:
    half_length = max(length, 0.1) / 2.0
    half_width = max(width, 0.1) / 2.0
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    corners = []
    for local_x, local_y in [
        (half_length, half_width),
        (half_length, -half_width),
        (-half_length, -half_width),
        (-half_length, half_width),
    ]:
        corners.append(
            (
                center_x + local_x * cos_yaw - local_y * sin_yaw,
                center_y + local_x * sin_yaw + local_y * cos_yaw,
            )
        )
    return corners


def _edges(points: list[Point2D]) -> list[tuple[Point2D, Point2D]]:
    return [(points[index], points[(index + 1) % len(points)]) for index in range(len(points))]


def _rectangle_axes(first: list[Point2D], second: list[Point2D]) -> list[Point2D]:
    axes = []
    for points in [first, second]:
        for start, end in _edges(points)[:2]:
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            norm = math.hypot(dx, dy)
            axes.append((-dy / norm, dx / norm))
    return axes


def _projection_gap(first: list[Point2D], second: list[Point2D], axis: Point2D) -> float:
    first_projection = [point[0] * axis[0] + point[1] * axis[1] for point in first]
    second_projection = [point[0] * axis[0] + point[1] * axis[1] for point in second]
    return max(
        min(second_projection) - max(first_projection),
        min(first_projection) - max(second_projection),
    )


def _segment_distance(a1: Point2D, a2: Point2D, b1: Point2D, b2: Point2D) -> float:
    if _segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        _point_segment_distance(a1, b1, b2),
        _point_segment_distance(a2, b1, b2),
        _point_segment_distance(b1, a1, a2),
        _point_segment_distance(b2, a1, a2),
    )


def _point_segment_distance(point: Point2D, start: Point2D, end: Point2D) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator == 0.0:
        return euclidean_distance(point[0], point[1], start[0], start[1])
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator
    ratio = max(0.0, min(1.0, ratio))
    projected = (start[0] + ratio * dx, start[1] + ratio * dy)
    return euclidean_distance(point[0], point[1], projected[0], projected[1])


def _segments_intersect(a1: Point2D, a2: Point2D, b1: Point2D, b2: Point2D) -> bool:
    def orientation(first: Point2D, second: Point2D, third: Point2D) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
            third[0] - first[0]
        )

    def on_segment(start: Point2D, point: Point2D, end: Point2D) -> bool:
        epsilon = 1e-9
        return (
            min(start[0], end[0]) - epsilon <= point[0] <= max(start[0], end[0]) + epsilon
            and min(start[1], end[1]) - epsilon <= point[1] <= max(start[1], end[1]) + epsilon
        )

    o1 = orientation(a1, a2, b1)
    o2 = orientation(a1, a2, b2)
    o3 = orientation(b1, b2, a1)
    o4 = orientation(b1, b2, a2)
    epsilon = 1e-9
    if o1 * o2 < -epsilon and o3 * o4 < -epsilon:
        return True
    return (
        (abs(o1) <= epsilon and on_segment(a1, b1, a2))
        or (abs(o2) <= epsilon and on_segment(a1, b2, a2))
        or (abs(o3) <= epsilon and on_segment(b1, a1, b2))
        or (abs(o4) <= epsilon and on_segment(b1, a2, b2))
    )
