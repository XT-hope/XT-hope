#!/usr/bin/env python3
"""
根据给定的 ELKA 超车场景数据计算：
1. B 车的起始中心坐标；
2. 碰撞瞬间 B 车的中心坐标；
3. B 车的航向（度，基于速度方向）。

所有输出均保留 4 位小数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


Point = Tuple[float, float]


def kmh_to_ms(kmh: float) -> float:
    return kmh / 3.6


@dataclass(frozen=True)
class Vehicle:
    length: float
    width: float
    rear_to_center: float
    front_to_center: float
    longitudinal_speed_kmh: float
    lateral_speed_ms: float
    initial_position: Point

    @property
    def longitudinal_speed_ms(self) -> float:
        return kmh_to_ms(self.longitudinal_speed_kmh)

    def contact_offset_from_center(self, distance_from_tail: float) -> float:
        return distance_from_tail - self.rear_to_center


def compute_lateral_contact_time(target: Vehicle, ego: Vehicle) -> float:
    relative_lateral_speed = ego.lateral_speed_ms - target.lateral_speed_ms
    if relative_lateral_speed <= 0:
        raise ValueError("横向相对速度必须大于 0，才能发生接触。")

    initial_gap = target.initial_position[1] - ego.initial_position[1]
    required_gap = (target.width + ego.width) / 2.0
    time = (initial_gap - required_gap) / relative_lateral_speed
    if time < 0:
        raise ValueError("计算得到的碰撞时间为负，检查输入数据。")
    return time


def compute_b_initial_x(
    target: Vehicle,
    ego: Vehicle,
    time_to_collision: float,
    distance_from_tail: float,
) -> float:
    contact_offset = ego.contact_offset_from_center(distance_from_tail)
    target_front_x = target.initial_position[0] + target.longitudinal_speed_ms * time_to_collision + target.front_to_center
    ego_translation = ego.longitudinal_speed_ms * time_to_collision
    return target_front_x - contact_offset - ego_translation


def advance_point(point: Point, vx: float, vy: float, duration: float) -> Point:
    return point[0] + vx * duration, point[1] + vy * duration


def format_point(point: Point) -> str:
    return f"({point[0]:.4f}, {point[1]:.4f})"


def main() -> None:
    target = Vehicle(
        length=4.7,
        width=1.8,
        rear_to_center=1.7,
        front_to_center=3.0,
        longitudinal_speed_kmh=60.0,
        lateral_speed_ms=0.0,
        initial_position=(-26.0, 3.5),
    )
    ego = Vehicle(
        length=5.0,
        width=1.8,
        rear_to_center=1.0,
        front_to_center=4.0,
        longitudinal_speed_kmh=50.0,
        lateral_speed_ms=0.3,
        initial_position=(0.0, 0.0),
    )
    contact_distance_from_tail = 1.25

    time_to_collision = compute_lateral_contact_time(target, ego)
    b_initial_x = compute_b_initial_x(target, ego, time_to_collision, contact_distance_from_tail)
    b_initial_center = (b_initial_x, ego.initial_position[1])
    b_collision_center = advance_point(
        b_initial_center, ego.longitudinal_speed_ms, ego.lateral_speed_ms, time_to_collision
    )
    heading_deg = math.degrees(math.atan2(ego.lateral_speed_ms, ego.longitudinal_speed_ms))

    print(f"碰撞时间 (s): {time_to_collision:.4f}")
    print(f"B 车起始中心坐标 (m): {format_point(b_initial_center)}")
    print(f"B 车碰撞中心坐标 (m): {format_point(b_collision_center)}")
    print(f"B 车航向角 (deg): {heading_deg:.4f}")


if __name__ == "__main__":
    main()
