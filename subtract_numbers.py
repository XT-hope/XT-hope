from typing import Union
from functools import wraps
import time

# 方法1: 基础函数实现
def subtract_two_numbers(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的差
    
    参数:
        a: 被减数 (int 或 float)
        b: 减数 (int 或 float)
    
    返回:
        两个数字的差 (a - b)
    """
    return a - b


# 方法2: 使用类的方式
class Calculator:
    """计算器类 - 支持减法运算"""
    
    def __init__(self):
        self.history = []
    
    def subtract(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """两数相减方法"""
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def get_history(self) -> list:
        """获取计算历史"""
        return self.history
    
    def clear_history(self):
        """清除计算历史"""
        self.history.clear()


# 方法3: 使用装饰器的函数
def log_operation(func):
    """记录操作的装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"操作: {func.__name__}({args[0]}, {args[1]}) = {result}")
        print(f"执行时间: {end_time - start_time:.6f}秒")
        return result
    return wrapper

@log_operation
def subtract_with_log(x: Union[int, float], y: Union[int, float]) -> Union[int, float]:
    """带日志记录的减法函数"""
    return x - y


# 方法4: 使用lambda表达式
subtract_lambda = lambda a, b: a - b


# 方法5: 支持连续减法的函数
def subtract_multiple(first_number: Union[int, float], *numbers: Union[int, float]) -> Union[int, float]:
    """
    支持连续减法运算
    
    参数:
        first_number: 初始被减数
        *numbers: 可变参数，要依次减去的数字
    
    返回:
        连续减法的结果
    """
    if not isinstance(first_number, (int, float)):
        raise TypeError(f"第一个参数必须是数字类型，但收到了 {type(first_number)}")
    
    result = first_number
    for num in numbers:
        if not isinstance(num, (int, float)):
            raise TypeError(f"所有参数必须是数字类型，但收到了 {type(num)}")
        result -= num
    
    return result


# 方法6: 使用静态方法
class MathUtils:
    """数学工具类 - 减法运算"""
    
    @staticmethod
    def subtract_two(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """静态方法实现两数相减"""
        return a - b
    
    @staticmethod
    def absolute_difference(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """计算两数的绝对差值"""
        return abs(a - b)
    
    @classmethod
    def create_subtractor(cls, base_number: Union[int, float]):
        """类方法：创建一个减法器"""
        def subtractor(x):
            return base_number - x
        return subtractor


# 方法7: 使用闭包
def create_subtract_function(minuend: Union[int, float]):
    """
    创建一个带固定被减数的减法函数（闭包）
    
    参数:
        minuend: 固定的被减数
    
    返回:
        减法函数
    """
    def subtract_from_minuend(subtrahend: Union[int, float]) -> Union[int, float]:
        return minuend - subtrahend
    
    return subtract_from_minuend


# 方法8: 带参数验证的减法函数
def safe_subtract(a: Union[int, float], b: Union[int, float], 
                 allow_negative: bool = True) -> Union[int, float]:
    """
    安全的减法函数，支持参数验证
    
    参数:
        a: 被减数
        b: 减数
        allow_negative: 是否允许负数结果
    
    返回:
        减法结果
    
    异常:
        ValueError: 当结果为负数且不允许负数时
        TypeError: 当参数不是数字类型时
    """
    # 类型检查
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    
    result = a - b
    
    # 负数检查
    if not allow_negative and result < 0:
        raise ValueError(f"结果为负数 ({result})，但不允许负数结果")
    
    return result


def main():
    """演示不同的减法实现方式"""
    
    print("=== 方法1: 基础函数实现 ===")
    result1 = subtract_two_numbers(20, 8)
    result2 = subtract_two_numbers(5.5, 2.3)
    print(f"20 - 8 = {result1}")
    print(f"5.5 - 2.3 = {result2}")
    
    print("\n=== 方法2: 使用类的方式 ===")
    calc = Calculator()
    calc_result1 = calc.subtract(50, 15)
    calc_result2 = calc.subtract(10.7, 3.2)
    print(f"类方法结果1: {calc_result1}")
    print(f"类方法结果2: {calc_result2}")
    print("计算历史:")
    for record in calc.get_history():
        print(f"  {record}")
    
    print("\n=== 方法3: 使用装饰器的函数 ===")
    subtract_with_log(100, 25)
    
    print("\n=== 方法4: 使用lambda表达式 ===")
    lambda_result = subtract_lambda(15, 7)
    print(f"Lambda结果: 15 - 7 = {lambda_result}")
    
    print("\n=== 方法5: 支持连续减法 ===")
    multi_result1 = subtract_multiple(100, 10, 20, 30)  # 100 - 10 - 20 - 30
    multi_result2 = subtract_multiple(50.5, 5.5, 10.5)  # 50.5 - 5.5 - 10.5
    print(f"连续减法1: 100 - 10 - 20 - 30 = {multi_result1}")
    print(f"连续减法2: 50.5 - 5.5 - 10.5 = {multi_result2}")
    
    print("\n=== 方法6: 使用静态方法 ===")
    static_result = MathUtils.subtract_two(30, 12)
    abs_diff = MathUtils.absolute_difference(5, 15)  # |5 - 15| = 10
    print(f"静态方法结果: 30 - 12 = {static_result}")
    print(f"绝对差值: |5 - 15| = {abs_diff}")
    
    # 创建一个以100为被减数的减法器
    subtract_from_100 = MathUtils.create_subtractor(100)
    subtractor_result = subtract_from_100(25)
    print(f"减法器结果: 100 - 25 = {subtractor_result}")
    
    print("\n=== 方法7: 使用闭包 ===")
    subtract_from_200 = create_subtract_function(200)
    closure_result = subtract_from_200(80)
    print(f"闭包结果: 200 - 80 = {closure_result}")
    
    print("\n=== 方法8: 带参数验证的减法 ===")
    try:
        safe_result1 = safe_subtract(20, 5)
        print(f"安全减法1: 20 - 5 = {safe_result1}")
        
        safe_result2 = safe_subtract(10, 15, allow_negative=True)
        print(f"安全减法2 (允许负数): 10 - 15 = {safe_result2}")
        
        # 这会抛出异常
        # safe_subtract(5, 10, allow_negative=False)
        
    except ValueError as e:
        print(f"错误: {e}")
    
    print("\n=== 用户交互示例 ===")
    try:
        print("请输入两个数字进行减法运算:")
        num1 = float(input("被减数: "))
        num2 = float(input("减数: "))
        interactive_result = subtract_two_numbers(num1, num2)
        print(f"结果: {num1} - {num2} = {interactive_result}")
    except ValueError:
        print("请输入有效的数字!")
    except KeyboardInterrupt:
        print("\n程序已取消")


if __name__ == "__main__":
    main()