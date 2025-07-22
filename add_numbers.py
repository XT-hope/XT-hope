def add_two_numbers(a, b):
    """
    计算两个数的和
    
    参数:
        a: 第一个数字 (int 或 float)
        b: 第二个数字 (int 或 float)
    
    返回:
        两个数字的和
    """
    return a + b


def main():
    """
    示例使用
    """
    # 示例1: 整数相加
    num1 = 5
    num2 = 3
    result1 = add_two_numbers(num1, num2)
    print(f"{num1} + {num2} = {result1}")
    
    # 示例2: 浮点数相加
    num3 = 2.5
    num4 = 3.7
    result2 = add_two_numbers(num3, num4)
    print(f"{num3} + {num4} = {result2}")
    
    # 示例3: 用户输入
    try:
        user_num1 = float(input("请输入第一个数字: "))
        user_num2 = float(input("请输入第二个数字: "))
        user_result = add_two_numbers(user_num1, user_num2)
        print(f"结果: {user_num1} + {user_num2} = {user_result}")
    except ValueError:
        print("请输入有效的数字!")


if __name__ == "__main__":
    main()