from __future__ import annotations

import math
from typing import Sequence


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
