#!/usr/bin/env python3
"""
sample_arc_points.py

无需命令行参数，直接在脚本顶部修改“配置区”即可。
根据给定的起点/终点 (x, y) 以及圆弧半径，均匀插值若干内部点并打印。
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Vec2 = Tuple[float, float]


# ======================== 配置区（按需修改） ======================== #
START_POINT: Vec2 = (0.0, 0.0)
END_POINT: Vec2 = (10.0, 10.0)
RADIUS = 20.0                 # 半径需 > 0
NUM_POINTS = 8                # 要插值的内部点数量
USE_ALTERNATE_CENTER = False  # 若为 True，采用另一侧圆心
TRAVEL_CCW = True             # True 表示沿逆时针方向走弧，False 表示顺时针
# ================================================================== #


def compute_circle_centers(start_xy: Vec2,
                           end_xy: Vec2,
                           radius: float) -> Tuple[Vec2, Vec2]:
    dx = end_xy[0] - start_xy[0]
    dy = end_xy[1] - start_xy[1]
    chord_length = math.hypot(dx, dy)
    if chord_length == 0:
        raise ValueError("起点与终点不能相同")
    if chord_length > 2 * radius + 1e-9:
        raise ValueError("给定半径不足以链接起终点（弦长 > 2*R）")

    mid = ((start_xy[0] + end_xy[0]) * 0.5,
           (start_xy[1] + end_xy[1]) * 0.5)
    half_chord = chord_length * 0.5

    # 数值容差处理：若 chord_length 接近 2R，则 sqrt 结果可能为 0
    offset = max(radius * radius - half_chord * half_chord, 0.0)
    height = math.sqrt(offset)

    # 正规化弦方向
    ux = dx / chord_length
    uy = dy / chord_length
    # 正交方向（逆时针旋转 90 度）
    perp = (-uy, ux)

    center1 = (mid[0] + height * perp[0],
               mid[1] + height * perp[1])
    center2 = (mid[0] - height * perp[0],
               mid[1] - height * perp[1])
    return center1, center2


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
                      end_xy: Vec2,
                      radius: float,
                      num_points: int,
                      use_alternate_center: bool,
                      travel_ccw: bool) -> List[Vec2]:
    if radius <= 0:
        raise ValueError("radius 必须为正数")
    if num_points <= 0:
        raise ValueError("num_points 必须为正整数")

    centers = compute_circle_centers(start_xy, end_xy, radius)
    center = centers[1] if use_alternate_center else centers[0]
    theta0 = math.atan2(start_xy[1] - center[1], start_xy[0] - center[0])
    theta1 = math.atan2(end_xy[1] - center[1], end_xy[0] - center[0])
    delta = signed_delta(theta0, theta1, travel_ccw)

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


def main() -> None:
    sampled = sample_arc_points(
        start_xy=START_POINT,
        end_xy=END_POINT,
        radius=RADIUS,
        num_points=NUM_POINTS,
        use_alternate_center=USE_ALTERNATE_CENTER,
        travel_ccw=TRAVEL_CCW,
    )
    format_points(sampled)


if __name__ == "__main__":
    main()
