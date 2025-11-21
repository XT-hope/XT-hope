#!/usr/bin/env python3
"""
sample_arc_points.py

无需命令行参数，直接在脚本顶部修改“配置区”即可。
根据给定的起点/终点 (x, y, yaw) 以及圆弧半径，均匀插值 8 个内部点并打印。
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Vec2 = Tuple[float, float]


# ======================== 配置区（按需修改） ======================== #
START_POINT: Vec2 = (0.0, 0.0)
START_YAW = 0.0          # 单位见 YAW_IN_DEGREES
END_POINT: Vec2 = (10.0, 10.0)
END_YAW = 90.0           # 单位见 YAW_IN_DEGREES
RADIUS = 20.0            # 半径 > 0
NUM_POINTS = 8           # 需要的内部点数量
YAW_IN_DEGREES = True    # True 表示上述 yaw 为度，False 表示弧度
# ================================================================== #


def heading_vector(yaw: float) -> Vec2:
    return math.cos(yaw), math.sin(yaw)


def tangent_from_radius(radius_vec: Vec2, ccw: bool) -> Vec2:
    tx, ty = (-radius_vec[1], radius_vec[0]) if ccw else (radius_vec[1], -radius_vec[0])
    norm = math.hypot(tx, ty)
    if norm == 0:
        raise ValueError("半径向量长度为 0，无法构造切向量")
    return tx / norm, ty / norm


def compute_center(start_xy: Vec2, start_yaw: float, radius: float, ccw: bool) -> Vec2:
    hx, hy = heading_vector(start_yaw)
    nx, ny = (-hy, hx) if ccw else (hy, -hx)
    return start_xy[0] + radius * nx, start_xy[1] + radius * ny


def select_circle(start_xy: Vec2,
                  start_yaw: float,
                  end_xy: Vec2,
                  end_yaw: float,
                  radius: float) -> Tuple[Vec2, bool]:
    start_heading = heading_vector(start_yaw)
    end_heading = heading_vector(end_yaw)

    best = None
    for ccw in (True, False):
        center = compute_center(start_xy, start_yaw, radius, ccw)
        r_start = (start_xy[0] - center[0], start_xy[1] - center[1])
        r_end = (end_xy[0] - center[0], end_xy[1] - center[1])
        start_tangent = tangent_from_radius(r_start, ccw)
        end_tangent = tangent_from_radius(r_end, ccw)
        start_align = 1 - max(-1.0, min(1.0, start_tangent[0] * start_heading[0] +
                                        start_tangent[1] * start_heading[1]))
        end_align = 1 - max(-1.0, min(1.0, end_tangent[0] * end_heading[0] +
                                      end_tangent[1] * end_heading[1]))
        radial_err = abs(math.hypot(*r_end) - radius)
        score = start_align + end_align + radial_err
        candidate = (score, center, ccw)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise RuntimeError("无法确定圆心")
    return best[1], best[2]


def signed_delta(theta0: float, theta1: float, ccw: bool) -> float:
    raw = theta1 - theta0
    if ccw:
        while raw <= 0:
            raw += 2 * math.pi
    else:
        while raw >= 0:
            raw -= 2 * math.pi
    return raw


def sample_arc_points(start_xy: Vec2,
                      start_yaw: float,
                      end_xy: Vec2,
                      end_yaw: float,
                      radius: float,
                      num_points: int) -> List[Vec2]:
    if radius <= 0:
        raise ValueError("radius 必须为正数")
    if num_points <= 0:
        raise ValueError("num_points 必须为正整数")

    center, ccw = select_circle(start_xy, start_yaw, end_xy, end_yaw, radius)
    theta0 = math.atan2(start_xy[1] - center[1], start_xy[0] - center[0])
    theta1 = math.atan2(end_xy[1] - center[1], end_xy[0] - center[0])
    delta = signed_delta(theta0, theta1, ccw)

    pts: List[Vec2] = []
    step = delta / (num_points + 1)
    for i in range(1, num_points + 1):
        theta = theta0 + i * step
        pts.append((center[0] + radius * math.cos(theta),
                    center[1] + radius * math.sin(theta)))
    return pts


def format_points(points: Sequence[Vec2]) -> None:
    for idx, (x, y) in enumerate(points, 1):
        print(f"point_{idx}: x={x:.6f}, y={y:.6f}")


def maybe_convert_yaw(yaw: float) -> float:
    return math.radians(yaw) if YAW_IN_DEGREES else yaw


def main() -> None:
    start_yaw = maybe_convert_yaw(START_YAW)
    end_yaw = maybe_convert_yaw(END_YAW)

    sampled = sample_arc_points(
        start_xy=START_POINT,
        start_yaw=start_yaw,
        end_xy=END_POINT,
        end_yaw=end_yaw,
        radius=RADIUS,
        num_points=NUM_POINTS,
    )
    format_points(sampled)


if __name__ == "__main__":
    main()
