from typing import Union, Any
from functools import wraps
import time

# 方法1: 使用类的方式
class Calculator:
    """计算器类"""
    
    def __init__(self):
        self.history = []
    
    def add(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """两数相加方法"""
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def get_history(self) -> list:
        """获取计算历史"""
        return self.history
    
    def clear_history(self):
        """清除计算历史"""
        self.history.clear()


# 方法2: 使用装饰器的函数
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
def add_with_log(x: Union[int, float], y: Union[int, float]) -> Union[int, float]:
    """带日志记录的加法函数"""
    return x + y


# 方法3: 使用lambda表达式
add_lambda = lambda a, b: a + b


# 方法4: 支持多个数字相加的函数
def add_multiple(*numbers: Union[int, float]) -> Union[int, float]:
    """
    支持多个数字相加
    
    参数:
        *numbers: 可变参数，支持传入多个数字
    
    返回:
        所有数字的和
    """
    if not numbers:
        return 0
    
    total = 0
    for num in numbers:
        if not isinstance(num, (int, float)):
            raise TypeError(f"所有参数必须是数字类型，但收到了 {type(num)}")
        total += num
    
    return total


# 方法5: 使用静态方法
class MathUtils:
    """数学工具类"""
    
    @staticmethod
    def add_two(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """静态方法实现两数相加"""
        return a + b
    
    @classmethod
    def create_adder(cls, base_number: Union[int, float]):
        """类方法：创建一个加法器"""
        def adder(x):
            return cls.add_two(base_number, x)
        return adder


# 方法6: 使用闭包
def create_add_function(initial_value: Union[int, float] = 0):
    """
    创建一个带初始值的加法函数（闭包）
    
    参数:
        initial_value: 初始值
    
    返回:
        加法函数
    """
    def add_to_initial(value: Union[int, float]) -> Union[int, float]:
        return initial_value + value
    
    return add_to_initial


def main():
    """演示不同的实现方式"""
    print("=== 方法1: 使用类的方式 ===")
    calc = Calculator()
    result1 = calc.add(10, 20)
    result2 = calc.add(5.5, 4.5)
    print(f"结果1: {result1}")
    print(f"结果2: {result2}")
    print("计算历史:")
    for record in calc.get_history():
        print(f"  {record}")
    
    print("\n=== 方法2: 使用装饰器的函数 ===")
    add_with_log(15, 25)
    
    print("\n=== 方法3: 使用lambda表达式 ===")
    lambda_result = add_lambda(7, 8)
    print(f"Lambda结果: 7 + 8 = {lambda_result}")
    
    print("\n=== 方法4: 支持多个数字相加 ===")
    multi_result1 = add_multiple(1, 2, 3, 4, 5)
    multi_result2 = add_multiple(10.5, 20.5, 30.5)
    print(f"多数相加1: 1+2+3+4+5 = {multi_result1}")
    print(f"多数相加2: 10.5+20.5+30.5 = {multi_result2}")
    
    print("\n=== 方法5: 使用静态方法 ===")
    static_result = MathUtils.add_two(12, 18)
    print(f"静态方法结果: 12 + 18 = {static_result}")
    
    # 创建一个以10为基数的加法器
    add_to_ten = MathUtils.create_adder(10)
    adder_result = add_to_ten(5)
    print(f"加法器结果: 10 + 5 = {adder_result}")
    
    print("\n=== 方法6: 使用闭包 ===")
    add_to_100 = create_add_function(100)
    closure_result = add_to_100(50)
    print(f"闭包结果: 100 + 50 = {closure_result}")


if __name__ == "__main__":
    main()