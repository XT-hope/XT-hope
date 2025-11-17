#!/usr/bin/env python3
"""
基于题述几何和速度约束，计算目标车 A 与测试车 B 在 ELKA overtaking 场景中的碰撞时间、
B 车碰撞时中心坐标、B 车起始中心坐标以及 B 车航向角。

输入参数:
    --a-speed-kmh:  A 车纵向速度，单位 km/h
    --b-long-speed-kmh: B 车纵向速度，单位 km/h
    --b-lat-speed-mps: B 车横向速度，单位 m/s（向 A 车方向）

几何假设:
    * A 车长 4.7 m (尾->中心 1.7 m, 头->中心 3.0 m)，宽 1.8 m。
    * B 车长 5.0 m (尾->中心 1.0 m, 头->中心 4.0 m)，宽 1.8 m。
    * A 车初始中心 (-26.0, 3.5)，B 车初始中心 (x, 0.0)，
      接触点位于 A 车右前角与 B 车左侧距车尾 1.25 m 处。
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Tuple

MPS_PER_KMH = 1000.0 / 3600.0


@dataclass(frozen=True)
class VehicleGeometry:
    length: float
    width: float
    tail_to_center: float
    head_to_center: float

    @property
    def half_width(self) -> float:
        return self.width / 2.0


A_GEOM = VehicleGeometry(length=4.7, width=1.8, tail_to_center=1.7, head_to_center=3.0)
B_GEOM = VehicleGeometry(length=5.0, width=1.8, tail_to_center=1.0, head_to_center=4.0)

X_A0 = -26.0
Y_A0 = 3.5
Y_B0 = 0.0
B_CONTACT_FROM_TAIL = 1.25


@dataclass(frozen=True)
class CollisionResult:
    time_to_collision: float
    heading_deg: float
    a_center_at_collision: Tuple[float, float]
    b_center_at_collision: Tuple[float, float]
    b_center_at_start: Tuple[float, float]


def kmh_to_mps(speed_kmh: float) -> float:
    return speed_kmh * MPS_PER_KMH


def lateral_contact_time(b_lat_speed_mps: float) -> float:
    if b_lat_speed_mps <= 0:
        raise ValueError("B 车横向速度必须为正，且方向指向 A 车。")

    lateral_gap = (Y_A0 - A_GEOM.half_width) - (Y_B0 + B_GEOM.half_width)
    if lateral_gap <= 0:
        raise ValueError("初始横向间距需大于 0，当前配置无解。")

    return lateral_gap / b_lat_speed_mps


def heading_deg(b_long_speed_kmh: float, b_lat_speed_mps: float) -> float:
    vx = kmh_to_mps(b_long_speed_kmh)
    if vx <= 0:
        raise ValueError("B 车纵向速度必须大于 0。")
    return math.degrees(math.atan2(b_lat_speed_mps, vx))


def compute_collision(
    a_speed_kmh: float, b_long_speed_kmh: float, b_lat_speed_mps: float
) -> CollisionResult:
    t = lateral_contact_time(b_lat_speed_mps)
    heading = heading_deg(b_long_speed_kmh, b_lat_speed_mps)

    v_a = kmh_to_mps(a_speed_kmh)
    v_b = kmh_to_mps(b_long_speed_kmh)

    x_a = X_A0 + v_a * t
    y_a = Y_A0

    contact_offset_rel_center = B_CONTACT_FROM_TAIL - B_GEOM.tail_to_center
    center_offset = A_GEOM.head_to_center - contact_offset_rel_center

    x_b = x_a + center_offset
    y_b = Y_B0 + b_lat_speed_mps * t

    x_b_start = x_b - v_b * t
    y_b_start = Y_B0

    return CollisionResult(
        time_to_collision=t,
        heading_deg=heading,
        a_center_at_collision=(x_a, y_a),
        b_center_at_collision=(x_b, y_b),
        b_center_at_start=(x_b_start, y_b_start),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算 ELKA overtaking 碰撞场景关键数据。")
    parser.add_argument("--a-speed-kmh", type=float, required=True, help="A 车纵向速度 (km/h)")
    parser.add_argument(
        "--b-long-speed-kmh", type=float, required=True, help="B 车纵向速度 (km/h)"
    )
    parser.add_argument(
        "--b-lat-speed-mps", type=float, required=True, help="B 车横向速度 (m/s)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = compute_collision(args.a_speed_kmh, args.b_long_speed_kmh, args.b_lat_speed_mps)

    print(f"碰撞时间: {result.time_to_collision:.6f} s")
    print(f"B 车航向: {result.heading_deg:.6f} deg")
    print(
        "A 车碰撞时中心: "
        f"({result.a_center_at_collision[0]:.6f}, {result.a_center_at_collision[1]:.6f}) m"
    )
    print(
        "B 车碰撞时中心: "
        f"({result.b_center_at_collision[0]:.6f}, {result.b_center_at_collision[1]:.6f}) m"
    )
    print(
        "B 车起始中心: "
        f"({result.b_center_at_start[0]:.6f}, {result.b_center_at_start[1]:.6f}) m"
    )


if __name__ == "__main__":
    main()
