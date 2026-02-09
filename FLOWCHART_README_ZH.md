# 信号流程控制框图设计与实现

完整的信号流程框图架构设计和PyQt6实现方案，包含Set Signal、Check Signal、Wait、Timeout、Duration、Async等所有流程控制元素。

## 项目文件概览

### 1. 设计文档（不需要编程）

| 文件 | 说明 | 适用人群 |
|------|------|----------|
| `signal_flow_architecture.md` | 详细的架构设计文档 | 架构师、设计师 |
| `signal_flow_diagrams.md` | Mermaid可视化图表 | 需要在线查看流程图 |
| `signal_flow_drawio_design.md` | Draw.io风格框图设计 | 使用Draw.io的用户 |

### 2. PyQt6实现代码（需要Python环境）

| 文件 | 方案 | 依赖 | 推荐度 |
|------|------|------|--------|
| `flowchart_editor.py` | PyQt6原生实现 | 仅PyQt6 | ⭐⭐⭐⭐⭐ |
| `flowchart_graphviz.py` | Graphviz集成 | PyQt6 + graphviz | ⭐⭐⭐⭐ |
| `flowchart_pyqtgraph.py` | PyQtGraph数据流 | PyQt6 + pyqtgraph | ⭐⭐⭐ |
| `quick_start_example.py` | 快速入门示例 | PyQt6 | ⭐⭐⭐⭐⭐ |

### 3. 说明文档

| 文件 | 说明 |
|------|------|
| `PYQT6_FLOWCHART_README.md` | PyQt6完整使用指南（推荐阅读） |
| `pyqt6_flowchart_solutions.md` | 方案对比概览 |
| `requirements.txt` | Python依赖列表 |

## 快速开始

### 方式1：使用设计文档（无需编程）

如果您只需要框图设计方案，不需要写代码：

1. 查看 `signal_flow_drawio_design.md` 获取Draw.io风格的框图设计
2. 查看 `signal_flow_diagrams.md` 获取Mermaid图表（可以在GitHub直接预览）
3. 查看 `signal_flow_architecture.md` 了解详细架构

### 方式2：运行PyQt6流程图编辑器（推荐）

```bash
# 1. 安装依赖
pip install PyQt6

# 2. 运行编辑器（包含示例流程图）
python flowchart_editor.py

# 或运行快速入门示例
python quick_start_example.py
```

### 方式3：使用Graphviz自动布局

```bash
# 1. 安装依赖
pip install PyQt6 graphviz

# 2. 安装系统Graphviz
# Ubuntu/Debian:
sudo apt install graphviz

# macOS:
brew install graphviz

# 3. 运行
python flowchart_graphviz.py
```

### 方式4：使用PyQtGraph数据流图

```bash
# 1. 安装依赖
pip install PyQt6 pyqtgraph

# 2. 运行
python flowchart_pyqtgraph.py
```

## 核心功能展示

### 支持的流程元素

所有实现方案都支持以下流程控制元素：

1. **Set Signal（设置信号）** - 圆角矩形，绿色
   - 用于设置或触发信号

2. **Check Signal（检查信号）** - 菱形，蓝色
   - 用于检查信号状态

3. **Wait（等待延迟）** - 平行四边形，黄色
   - 固定时间延迟

4. **Timeout（超时控制）** - 六边形，橙色
   - 设置操作的最大等待时间

5. **Duration（持续检测）** - 双线矩形，紫色
   - 在指定时间段内持续监控

6. **Async Task（异步任务）** - 圆柱体，青色
   - 并行执行多个操作

7. **Decision（判断）** - 菱形，灰色
   - 条件判断节点

8. **Start/End（开始/结束）** - 椭圆，深灰色
   - 流程起点和终点

### 连接线类型

- **普通流程** - 黑色实线：正常顺序执行
- **超时触发** - 红色虚线：超时触发的流程
- **异步调用** - 蓝色粗线：异步并行执行
- **循环返回** - 灰色点线：循环返回

## 实际应用场景

### 场景1：设备初始化检测
```
开始 → Set Signal(ready=False) → Wait(2s) → Check Signal(ready?) 
→ Decision → Success / Timeout
```

### 场景2：多传感器数据验证
```
主流程 → 创建异步任务组
  ├─ Async Task 1 → Check Sensor A
  ├─ Async Task 2 → Check Sensor B
  └─ Async Task 3 → Check Sensor C
→ Wait All → 汇总结果 → 结束
```

### 场景3：稳定性监控
```
开始 → Duration(30s) → Check Signal(循环) → 记录结果 
→ 统计分析 → 输出报告
```

## 编程示例

### 示例1：创建基础流程图

```python
from flowchart_editor import *

app = QApplication(sys.argv)
editor = FlowchartEditor()

# 创建节点
start = StartEndNode(200, 100, "开始")
set_signal = SetSignalNode(200, 200)
check = CheckSignalNode(200, 300)
end = StartEndNode(200, 400, "结束")

# 添加到场景
for node in [start, set_signal, check, end]:
    editor.scene.addItem(node)

# 创建连接
editor.scene.addItem(ConnectionLine(start, set_signal))
editor.scene.addItem(ConnectionLine(set_signal, check))
editor.scene.addItem(ConnectionLine(check, end))

editor.show()
app.exec()
```

### 示例2：使用Graphviz生成流程图

```python
from flowchart_graphviz import *

app = QApplication(sys.argv)
viewer = GraphvizFlowchartViewer()

dot_code = """
digraph MyFlow {
    start [label="开始", shape=ellipse];
    set [label="Set Signal", shape=box];
    check [label="Check Signal", shape=diamond];
    end [label="结束", shape=ellipse];
    
    start -> set -> check -> end;
}
"""

viewer.code_editor.setText(dot_code)
viewer.render_flowchart()
viewer.show()
app.exec()
```

## 推荐学习路径

### 初学者
1. 先运行 `flowchart_editor.py` 查看效果
2. 阅读 `PYQT6_FLOWCHART_README.md` 了解基本概念
3. 运行 `quick_start_example.py` 学习编程方式
4. 修改示例代码，创建自己的流程图

### 进阶用户
1. 查看 `signal_flow_architecture.md` 理解架构设计
2. 阅读源码了解实现细节
3. 根据需求选择合适的方案（原生/Graphviz/PyQtGraph）
4. 扩展和自定义节点类型

### 设计师/架构师
1. 查看 `signal_flow_drawio_design.md` 获取设计规范
2. 使用 `signal_flow_diagrams.md` 中的Mermaid图表
3. 参考 `signal_flow_architecture.md` 进行架构设计

## 常见问题

### Q: 我只想要框图设计，不想写代码？
A: 查看 `signal_flow_drawio_design.md`，里面有完整的Draw.io风格设计方案。

### Q: 哪个实现方案最好？
A: 
- 需要完整编辑器：`flowchart_editor.py`（PyQt6原生）
- 需要自动布局：`flowchart_graphviz.py`
- 处理数据流：`flowchart_pyqtgraph.py`

### Q: 如何快速上手？
A: 先运行 `quick_start_example.py`，然后阅读 `PYQT6_FLOWCHART_README.md`。

### Q: 可以导出图片吗？
A: 可以。PyQt6原生方案支持导出PNG/SVG，Graphviz支持多种格式。

### Q: 如何修改节点颜色和样式？
A: 在代码中修改 `colors` 字典或重写 `_draw_shape()` 方法。详见使用文档。

## 项目特点

1. **完整性**：从设计到实现的完整方案
2. **多样性**：提供3种不同的实现方式
3. **实用性**：包含真实应用场景示例
4. **可扩展**：易于自定义和扩展
5. **文档齐全**：详细的文档和注释
6. **中文友好**：所有文档和界面均为中文

## 技术栈

- **PyQt6**：现代化的Python GUI框架
- **Graphviz**：专业的图形可视化工具
- **PyQtGraph**：高性能科学图形库
- **Mermaid**：Markdown中的图表语法

## 适用领域

- 自动化测试流程设计
- 信号处理系统架构
- 设备控制流程
- 状态机设计
- 工作流管理
- 数据处理管道
- 系统架构设计

## 贡献与反馈

如有问题或建议，欢迎反馈！

## 许可证

本项目文件可自由使用和修改。

---

**开始使用：**
```bash
pip install PyQt6
python flowchart_editor.py
```

**查看文档：**
- 完整指南：`PYQT6_FLOWCHART_README.md`
- 架构设计：`signal_flow_architecture.md`
- 快速示例：`quick_start_example.py`
