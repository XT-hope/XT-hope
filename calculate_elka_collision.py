"""
计算ELKA overtaking碰撞场景的坐标

场景描述：
- A车（目标车）和B车（测试车）沿X正方向行驶
- B车纵向速度：50 km/h（恒定），横向速度：0.3 km/h（向A车靠近，恒定）
- A车纵向速度：60 km/h（恒定），横向速度：0
- A车尺寸：长4.7m，宽1.8m，中心点在车长1.7:3处（车尾距中心1.7m，车头距中心3m）
- B车尺寸：长5m，宽1.8m，中心点在车长1:4处（车尾距中心1m，车头距中心4m）
- A车初始位置（中心点）：(-26, 3.5)
- B车初始位置（中心点）：(x_B0, 0)，需要计算
- 碰撞点：A车右上顶点 与 B车左侧边框距车尾1.25m处
"""

def calculate_collision_coordinates():
    # 车辆参数
    # A车
    car_a_length = 4.7  # m
    car_a_width = 1.8   # m
    car_a_rear_to_center = 1.7  # m
    car_a_front_to_center = 3.0  # m
    car_a_initial_x = -26  # m
    car_a_initial_y = 3.5  # m
    car_a_vx = 60  # km/h
    car_a_vy = 0   # km/h
    
    # B车
    car_b_length = 5.0  # m
    car_b_width = 1.8   # m
    car_b_rear_to_center = 1.0  # m
    car_b_front_to_center = 4.0  # m
    car_b_initial_y = 0  # m
    car_b_vx = 50  # km/h
    car_b_vy = 0.3  # km/h
    
    # 碰撞点在B车左侧边框距车尾的距离
    collision_point_from_b_rear = 1.25  # m
    
    print("=" * 60)
    print("ELKA Overtaking 碰撞场景坐标计算")
    print("=" * 60)
    
    # 转换速度单位为 m/h
    car_a_vx_m_per_h = car_a_vx * 1000  # m/h
    car_b_vx_m_per_h = car_b_vx * 1000  # m/h
    car_b_vy_m_per_h = car_b_vy * 1000  # m/h
    
    # A车右上顶点位置（固定在A车车架上的点）
    # 右侧：y方向减去半车宽
    # 顶点（车头）：x方向加上车头到中心的距离
    car_a_right_y_offset = -car_a_width / 2  # 相对于中心点
    car_a_front_x_offset = car_a_front_to_center  # 相对于中心点
    
    # B车左侧边框碰撞点（固定在B车车架上的点）
    # 左侧：y方向加上半车宽
    # 距车尾1.25m：x方向为 -(车尾到中心距离) + 1.25
    car_b_left_y_offset = car_b_width / 2  # 相对于中心点
    car_b_collision_x_offset = -car_b_rear_to_center + collision_point_from_b_rear  # 相对于中心点
    
    print("\n车辆参数：")
    print(f"A车尺寸：长{car_a_length}m × 宽{car_a_width}m")
    print(f"A车中心定义：车尾{car_a_rear_to_center}m | 中心 | 车头{car_a_front_to_center}m")
    print(f"A车初始中心位置：({car_a_initial_x}, {car_a_initial_y})")
    print(f"A车速度：纵向{car_a_vx} km/h，横向{car_a_vy} km/h")
    print()
    print(f"B车尺寸：长{car_b_length}m × 宽{car_b_width}m")
    print(f"B车中心定义：车尾{car_b_rear_to_center}m | 中心 | 车头{car_b_front_to_center}m")
    print(f"B车初始中心位置：(x_B0, {car_b_initial_y})")
    print(f"B车速度：纵向{car_b_vx} km/h，横向{car_b_vy} km/h")
    print()
    print(f"碰撞要求：A车右上顶点 与 B车左侧边框距车尾{collision_point_from_b_rear}m处")
    
    # 建立碰撞方程
    # 设碰撞发生在时刻t（单位：小时）
    
    # A车右上顶点在时刻t的坐标：
    # x_A_corner(t) = car_a_initial_x + car_a_vx_m_per_h * t + car_a_front_x_offset
    # y_A_corner(t) = car_a_initial_y + 0 * t + car_a_right_y_offset
    
    # B车左侧碰撞点在时刻t的坐标：
    # x_B_collision(t) = x_B0 + car_b_vx_m_per_h * t + car_b_collision_x_offset
    # y_B_collision(t) = car_b_initial_y + car_b_vy_m_per_h * t + car_b_left_y_offset
    
    # 碰撞条件：两点重合
    # x_A_corner(t) = x_B_collision(t)
    # y_A_corner(t) = y_B_collision(t)
    
    # 从y方向方程求解t：
    # car_a_initial_y + car_a_right_y_offset = car_b_initial_y + car_b_vy_m_per_h * t + car_b_left_y_offset
    y_A_corner = car_a_initial_y + car_a_right_y_offset
    y_B_initial = car_b_initial_y + car_b_left_y_offset
    
    t_collision = (y_A_corner - y_B_initial) / car_b_vy_m_per_h
    
    print("\n" + "=" * 60)
    print("求解过程：")
    print("=" * 60)
    print(f"\n步骤1：从y方向碰撞条件求解时间t")
    print(f"A车右上顶点的y坐标（固定）：{y_A_corner:.2f} m")
    print(f"B车左侧边框初始y坐标：{y_B_initial:.2f} m")
    print(f"B车横向速度：{car_b_vy_m_per_h:.2f} m/h")
    print(f"碰撞时间：t = ({y_A_corner:.2f} - {y_B_initial:.2f}) / {car_b_vy_m_per_h:.2f}")
    print(f"        t = {t_collision:.8f} 小时")
    print(f"        t = {t_collision * 3600:.4f} 秒")
    
    # 从x方向方程求解x_B0：
    # car_a_initial_x + car_a_vx_m_per_h * t + car_a_front_x_offset = x_B0 + car_b_vx_m_per_h * t + car_b_collision_x_offset
    x_A_corner_at_collision = car_a_initial_x + car_a_vx_m_per_h * t_collision + car_a_front_x_offset
    x_B0 = x_A_corner_at_collision - car_b_vx_m_per_h * t_collision - car_b_collision_x_offset
    
    print(f"\n步骤2：从x方向碰撞条件求解B车初始位置x_B0")
    print(f"碰撞时A车右上顶点的x坐标：{x_A_corner_at_collision:.4f} m")
    print(f"B车在t时刻的x位移：{car_b_vx_m_per_h * t_collision:.4f} m")
    print(f"B车碰撞点相对中心的x偏移：{car_b_collision_x_offset:.2f} m")
    print(f"B车初始x坐标：x_B0 = {x_B0:.4f} m")
    
    # 计算碰撞时B车的中心坐标
    x_B_center_at_collision = x_B0 + car_b_vx_m_per_h * t_collision
    y_B_center_at_collision = car_b_initial_y + car_b_vy_m_per_h * t_collision
    
    # 计算碰撞时A车的中心坐标（用于验证）
    x_A_center_at_collision = car_a_initial_x + car_a_vx_m_per_h * t_collision
    y_A_center_at_collision = car_a_initial_y
    
    print("\n" + "=" * 60)
    print("计算结果：")
    print("=" * 60)
    print(f"\nB车初始中心点坐标：({x_B0:.4f}, {car_b_initial_y:.4f}) m")
    print(f"\n碰撞时刻：t = {t_collision:.8f} 小时 = {t_collision * 3600:.4f} 秒")
    print(f"\n碰撞时B车中心点坐标：({x_B_center_at_collision:.4f}, {y_B_center_at_collision:.4f}) m")
    
    print("\n" + "=" * 60)
    print("验证计算结果：")
    print("=" * 60)
    
    # 验证碰撞点坐标
    collision_x = x_A_corner_at_collision
    collision_y = y_A_corner
    
    print(f"\n碰撞点坐标：({collision_x:.4f}, {collision_y:.4f}) m")
    
    print(f"\n验证A车右上顶点：")
    print(f"  A车碰撞时中心：({x_A_center_at_collision:.4f}, {y_A_center_at_collision:.4f})")
    print(f"  右上顶点坐标：({x_A_center_at_collision + car_a_front_x_offset:.4f}, {y_A_center_at_collision + car_a_right_y_offset:.4f})")
    
    print(f"\n验证B车左侧碰撞点：")
    print(f"  B车碰撞时中心：({x_B_center_at_collision:.4f}, {y_B_center_at_collision:.4f})")
    print(f"  左侧碰撞点坐标：({x_B_center_at_collision + car_b_collision_x_offset:.4f}, {y_B_center_at_collision + car_b_left_y_offset:.4f})")
    
    # 验证初始横向距离
    initial_lateral_distance = abs(car_a_initial_y - car_b_initial_y)
    print(f"\n验证初始横向距离（中心到中心）：{initial_lateral_distance:.2f} m")
    
    # 计算行驶距离
    distance_a = car_a_vx_m_per_h * t_collision
    distance_b_x = car_b_vx_m_per_h * t_collision
    distance_b_y = car_b_vy_m_per_h * t_collision
    
    print(f"\n到达碰撞点的行驶距离：")
    print(f"  A车纵向行驶：{distance_a:.4f} m")
    print(f"  B车纵向行驶：{distance_b_x:.4f} m")
    print(f"  B车横向行驶：{distance_b_y:.4f} m")
    
    print("\n" + "=" * 60)
    print("最终答案：")
    print("=" * 60)
    print(f"\n1. B车起始中心点坐标：({x_B0:.4f}, {car_b_initial_y:.4f}) m")
    print(f"   四舍五入到小数点后2位：({x_B0:.2f}, {car_b_initial_y:.2f}) m")
    print(f"\n2. 碰撞时B车中心点坐标：({x_B_center_at_collision:.4f}, {y_B_center_at_collision:.4f}) m")
    print(f"   四舍五入到小数点后2位：({x_B_center_at_collision:.2f}, {y_B_center_at_collision:.2f}) m")
    print(f"\n3. 碰撞点坐标：({collision_x:.4f}, {collision_y:.4f}) m")
    print(f"   四舍五入到小数点后2位：({collision_x:.2f}, {collision_y:.2f}) m")
    print(f"\n4. 碰撞时刻：{t_collision * 3600:.4f} 秒（{t_collision:.8f} 小时）")
    print("\n" + "=" * 60)
    
    return {
        'b_initial_center': (x_B0, car_b_initial_y),
        'b_collision_center': (x_B_center_at_collision, y_B_center_at_collision),
        'collision_point': (collision_x, collision_y),
        'collision_time_hours': t_collision,
        'collision_time_seconds': t_collision * 3600
    }


if __name__ == "__main__":
    result = calculate_collision_coordinates()
