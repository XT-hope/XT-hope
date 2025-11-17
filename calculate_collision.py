#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算ELKA overtaking功能测试中的车辆碰撞坐标
"""
import math


class Vehicle:
    """车辆类"""
    
    def __init__(self, length, width, center_to_rear, center_to_front):
        """
        初始化车辆参数
        
        Args:
            length: 车辆长度(m)
            width: 车辆宽度(m)
            center_to_rear: 车辆中心到车尾的距离(m)
            center_to_front: 车辆中心到车头的距离(m)
        """
        self.length = length
        self.width = width
        self.center_to_rear = center_to_rear
        self.center_to_front = center_to_front
        
    def get_corners(self, center_x, center_y):
        """
        获取车辆四个顶点坐标
        
        Args:
            center_x: 车辆中心x坐标
            center_y: 车辆中心y坐标
            
        Returns:
            dict: 四个顶点坐标 {'front_left', 'front_right', 'rear_left', 'rear_right'}
        """
        half_width = self.width / 2
        
        corners = {
            'front_left': (center_x + self.center_to_front, center_y - half_width),
            'front_right': (center_x + self.center_to_front, center_y + half_width),
            'rear_left': (center_x - self.center_to_rear, center_y - half_width),
            'rear_right': (center_x - self.center_to_rear, center_y + half_width)
        }
        
        return corners
    
    def get_position_at_time(self, initial_x, initial_y, vx, vy, t):
        """
        计算车辆在时间t时的位置
        
        Args:
            initial_x: 初始x坐标
            initial_y: 初始y坐标
            vx: x方向速度(m/s)
            vy: y方向速度(m/s)
            t: 时间(s)
            
        Returns:
            tuple: (x, y)坐标
        """
        x = initial_x + vx * t
        y = initial_y + vy * t
        return x, y


def calculate_collision_coordinates():
    """
    计算碰撞点的车辆坐标
    
    Returns:
        dict: 包含起始坐标和碰撞坐标的字典
    """
    
    # 车辆参数
    vehicle_a = Vehicle(length=4.7, width=1.8, center_to_rear=1.7, center_to_front=3.0)
    vehicle_b = Vehicle(length=5.0, width=1.8, center_to_rear=1.0, center_to_front=4.0)
    
    # A车初始位置
    a_initial_x = -26.0
    a_initial_y = 3.5
    
    # 速度转换：km/h -> m/s
    a_vx = 60.0 / 3.6  # 16.67 m/s
    a_vy = 0.0
    
    b_vx = 50.0 / 3.6  # 13.89 m/s
    b_vy = 0.3  # m/s (向A车靠近，y方向正向)
    
    # B车初始y坐标
    b_initial_y = 0.0
    
    # 计算B车的heading角（航向角）
    # heading = arctan(vy / vx)，结果为弧度
    b_heading_rad = math.atan2(b_vy, b_vx)
    b_heading_deg = math.degrees(b_heading_rad)
    
    # 初始横向距离
    lateral_distance = abs(a_initial_y - b_initial_y)
    
    print("=" * 60)
    print("车辆参数")
    print("=" * 60)
    print(f"A车（目标车）：")
    print(f"  尺寸：长{vehicle_a.length}m × 宽{vehicle_a.width}m")
    print(f"  中心位置：车尾{vehicle_a.center_to_rear}m | 车头{vehicle_a.center_to_front}m")
    print(f"  速度：纵向{60}km/h ({a_vx:.2f}m/s)，横向{a_vy}m/s")
    print(f"  初始位置：({a_initial_x}, {a_initial_y})")
    print()
    print(f"B车（测试车）：")
    print(f"  尺寸：长{vehicle_b.length}m × 宽{vehicle_b.width}m")
    print(f"  中心位置：车尾{vehicle_b.center_to_rear}m | 车头{vehicle_b.center_to_front}m")
    print(f"  速度：纵向{50}km/h ({b_vx:.2f}m/s)，横向{b_vy}m/s")
    print(f"  航向角(Heading)：{b_heading_deg:.4f}度 ({b_heading_rad:.6f}弧度)")
    print(f"  速度矢量方向：与X轴正方向夹角{b_heading_deg:.4f}度")
    print()
    print(f"初始横向距离：{lateral_distance}m")
    print()
    
    # 碰撞点条件：
    # A车的右上顶点 = B车左侧边框距离车尾1.25m处
    
    # A车右上顶点的y坐标（不随时间变化）
    a_right_top_y = a_initial_y + vehicle_a.width / 2  # 3.5 + 0.9 = 4.4
    
    # B车左侧边框的y坐标 = B车中心y - 车宽/2
    # 碰撞条件：a_right_top_y = b_center_y - vehicle_b.width / 2
    # 4.4 = b_initial_y + b_vy * t - 0.9
    # 4.4 = 0 + 0.3 * t - 0.9
    # 0.3 * t = 5.3
    
    collision_time = (a_right_top_y - b_initial_y + vehicle_b.width / 2) / b_vy
    
    print("=" * 60)
    print("碰撞条件计算")
    print("=" * 60)
    print(f"碰撞点：A车右上顶点 与 B车左侧边框（距车尾1.25m处）")
    print(f"A车右上顶点y坐标：{a_right_top_y}m（固定）")
    print(f"B车需要横向移动的距离：{a_right_top_y - b_initial_y - vehicle_b.width / 2:.2f}m")
    print(f"碰撞时间：{collision_time:.2f}秒")
    print()
    
    # 计算碰撞时刻A车的位置
    a_collision_x, a_collision_y = vehicle_a.get_position_at_time(
        a_initial_x, a_initial_y, a_vx, a_vy, collision_time
    )
    
    # A车在碰撞时刻的右上顶点x坐标
    a_right_top_x = a_collision_x + vehicle_a.center_to_front
    
    # B车左侧边框距离车尾1.25m处的x坐标（相对于B车中心）
    # B车中心到车尾1m，车尾后1.25m，所以相对中心是 -1 + 1.25 = 0.25m
    b_collision_point_offset = -vehicle_b.center_to_rear + 1.25
    
    # 碰撞点的x坐标条件：
    # a_right_top_x = b_collision_x + b_collision_point_offset
    # a_right_top_x = b_initial_x + b_vx * collision_time + 0.25
    
    b_initial_x = a_right_top_x - b_vx * collision_time - b_collision_point_offset
    
    # 计算碰撞时刻B车的位置
    b_collision_x, b_collision_y = vehicle_b.get_position_at_time(
        b_initial_x, b_initial_y, b_vx, b_vy, collision_time
    )
    
    print("=" * 60)
    print("计算结果")
    print("=" * 60)
    print(f"\nB车起始位置（中心点）：")
    print(f"  x = {b_initial_x:.2f}m")
    print(f"  y = {b_initial_y:.2f}m")
    print(f"  坐标：({b_initial_x:.2f}, {b_initial_y:.2f})")
    print(f"  航向角(Heading)：{b_heading_deg:.4f}度 ({b_heading_rad:.6f}弧度)")
    print()
    print(f"碰撞时B车中心点位置：")
    print(f"  x = {b_collision_x:.2f}m")
    print(f"  y = {b_collision_y:.2f}m")
    print(f"  坐标：({b_collision_x:.2f}, {b_collision_y:.2f})")
    print(f"  航向角(Heading)：{b_heading_deg:.4f}度 ({b_heading_rad:.6f}弧度)")
    print()
    
    # 验证碰撞点
    print("=" * 60)
    print("碰撞点验证")
    print("=" * 60)
    
    # A车右上顶点
    a_collision_corners = vehicle_a.get_corners(a_collision_x, a_collision_y)
    print(f"A车右上顶点：({a_collision_corners['front_right'][0]:.2f}, "
          f"{a_collision_corners['front_right'][1]:.2f})")
    
    # B车碰撞点（左侧边框距车尾1.25m处）
    b_collision_point_x = b_collision_x + b_collision_point_offset
    b_collision_point_y = b_collision_y - vehicle_b.width / 2
    print(f"B车左侧边框（距车尾1.25m）：({b_collision_point_x:.2f}, {b_collision_point_y:.2f})")
    
    # 检查是否匹配
    x_diff = abs(a_collision_corners['front_right'][0] - b_collision_point_x)
    y_diff = abs(a_collision_corners['front_right'][1] - b_collision_point_y)
    print(f"\n坐标差异：dx = {x_diff:.6f}m, dy = {y_diff:.6f}m")
    
    if x_diff < 0.01 and y_diff < 0.01:
        print("碰撞点计算正确")
    else:
        print("警告：碰撞点可能存在误差")
    
    print()
    print("=" * 60)
    print("运动轨迹信息")
    print("=" * 60)
    print(f"A车纵向移动距离：{a_vx * collision_time:.2f}m")
    print(f"B车纵向移动距离：{b_vx * collision_time:.2f}m")
    print(f"B车横向移动距离：{b_vy * collision_time:.2f}m")
    print(f"两车纵向相对速度：{(a_vx - b_vx) * 3.6:.2f}km/h ({a_vx - b_vx:.2f}m/s)")
    print()
    
    return {
        'b_start_position': (b_initial_x, b_initial_y),
        'b_collision_position': (b_collision_x, b_collision_y),
        'collision_time': collision_time,
        'collision_point': (b_collision_point_x, b_collision_point_y)
    }


if __name__ == '__main__':
    result = calculate_collision_coordinates()
