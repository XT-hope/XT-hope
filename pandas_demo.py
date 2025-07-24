import pandas as pd

# 读取Excel文件
data = pd.read_excel("data.xlsx")

# 错误的方式（会报错）：
# row1 = data[0, :]  # 这样不行，会报TypeError

# 正确的方式有几种：

# 方法1：使用iloc（推荐）
row1 = data.iloc[0]  # 获取第一行，返回Series
print("方法1 - 使用iloc:")
print(row1)
print(f"数据类型: {type(row1)}")
print()

# 方法2：使用iloc获取DataFrame格式
row1_df = data.iloc[0:1]  # 获取第一行，返回DataFrame
print("方法2 - 使用iloc返回DataFrame:")
print(row1_df)
print(f"数据类型: {type(row1_df)}")
print()

# 方法3：使用head()获取第一行
row1_head = data.head(1)  # 获取第一行，返回DataFrame
print("方法3 - 使用head(1):")
print(row1_head)
print()

# 方法4：如果想要所有列的第一行作为数组
row1_values = data.iloc[0].values  # 获取第一行的值作为numpy数组
print("方法4 - 获取第一行的值:")
print(row1_values)
print(f"数据类型: {type(row1_values)}")
print()

# 访问第一行的特定列
if len(data.columns) > 0:
    first_column_first_row = data.iloc[0, 0]  # 第一行第一列
    print(f"第一行第一列的值: {first_column_first_row}")
    
    # 如果知道列名
    if 'column_name' in data.columns:
        value = data.loc[0, 'column_name']  # 使用列名访问
        print(f"使用列名访问: {value}")