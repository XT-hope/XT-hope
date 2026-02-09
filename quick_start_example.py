"""
快速入门示例：创建一个完整的信号检测流程图
展示如何使用flowchart_editor模块快速构建流程图
"""

import sys
from PyQt6.QtWidgets import QApplication
from flowchart_editor import (
    FlowchartEditor,
    StartEndNode,
    SetSignalNode,
    WaitNode,
    TimeoutNode,
    CheckSignalNode,
    DecisionNode,
    DurationNode,
    AsyncTaskNode,
    ConnectionLine
)


def create_basic_signal_flow(editor):
    """创建基础信号检测流程"""
    print("创建基础信号检测流程...")
    
    # 清空现有场景
    editor.scene.clear()
    
    # 创建节点
    start = StartEndNode(400, 100, "开始")
    set_signal = SetSignalNode(400, 220)
    wait = WaitNode(400, 340)
    check = CheckSignalNode(400, 460)
    decision = DecisionNode(400, 580)
    success = StartEndNode(300, 700, "成功")
    fail = StartEndNode(500, 700, "失败")
    
    # 添加到场景
    nodes = [start, set_signal, wait, check, decision, success, fail]
    for node in nodes:
        editor.scene.addItem(node)
    
    # 创建连接
    editor.scene.addItem(ConnectionLine(start, set_signal, "normal"))
    editor.scene.addItem(ConnectionLine(set_signal, wait, "normal"))
    editor.scene.addItem(ConnectionLine(wait, check, "normal"))
    editor.scene.addItem(ConnectionLine(check, decision, "normal"))
    editor.scene.addItem(ConnectionLine(decision, success, "normal"))
    editor.scene.addItem(ConnectionLine(decision, fail, "normal"))
    
    print("✓ 基础流程创建完成")


def create_timeout_flow(editor):
    """创建带超时控制的流程"""
    print("创建带超时控制的流程...")
    
    editor.scene.clear()
    
    # 创建节点
    start = StartEndNode(400, 100, "开始")
    set_signal = SetSignalNode(400, 220)
    timeout = TimeoutNode(600, 340)
    wait = WaitNode(200, 340)
    check = CheckSignalNode(400, 460)
    decision = DecisionNode(400, 580)
    success = StartEndNode(300, 700, "成功")
    timeout_fail = StartEndNode(500, 700, "超时")
    
    # 添加到场景
    for node in [start, set_signal, timeout, wait, check, decision, success, timeout_fail]:
        editor.scene.addItem(node)
    
    # 创建连接
    editor.scene.addItem(ConnectionLine(start, set_signal))
    editor.scene.addItem(ConnectionLine(set_signal, wait))
    editor.scene.addItem(ConnectionLine(wait, check))
    editor.scene.addItem(ConnectionLine(timeout, check, "timeout"))  # 超时线
    editor.scene.addItem(ConnectionLine(check, decision))
    editor.scene.addItem(ConnectionLine(decision, success))
    editor.scene.addItem(ConnectionLine(decision, timeout_fail))
    
    print("✓ 超时控制流程创建完成")


def create_async_parallel_flow(editor):
    """创建异步并行流程"""
    print("创建异步并行流程...")
    
    editor.scene.clear()
    
    # 主流程
    start = StartEndNode(400, 80, "主流程")
    create_tasks = SetSignalNode(400, 200)
    
    # 三个异步任务
    task1 = AsyncTaskNode(150, 350)
    task2 = AsyncTaskNode(400, 350)
    task3 = AsyncTaskNode(650, 350)
    
    # 检查节点
    check1 = CheckSignalNode(150, 500)
    check2 = CheckSignalNode(400, 500)
    check3 = CheckSignalNode(650, 500)
    
    # 汇总和结束
    wait_all = SetSignalNode(400, 650)
    decision = DecisionNode(400, 770)
    end = StartEndNode(400, 890, "结束")
    
    # 添加节点
    nodes = [start, create_tasks, 
             task1, task2, task3,
             check1, check2, check3,
             wait_all, decision, end]
    
    for node in nodes:
        editor.scene.addItem(node)
    
    # 创建连接
    editor.scene.addItem(ConnectionLine(start, create_tasks))
    
    # 异步连接
    editor.scene.addItem(ConnectionLine(create_tasks, task1, "async"))
    editor.scene.addItem(ConnectionLine(create_tasks, task2, "async"))
    editor.scene.addItem(ConnectionLine(create_tasks, task3, "async"))
    
    editor.scene.addItem(ConnectionLine(task1, check1))
    editor.scene.addItem(ConnectionLine(task2, check2))
    editor.scene.addItem(ConnectionLine(task3, check3))
    
    editor.scene.addItem(ConnectionLine(check1, wait_all))
    editor.scene.addItem(ConnectionLine(check2, wait_all))
    editor.scene.addItem(ConnectionLine(check3, wait_all))
    
    editor.scene.addItem(ConnectionLine(wait_all, decision))
    editor.scene.addItem(ConnectionLine(decision, end))
    
    print("✓ 异步并行流程创建完成")


def create_duration_check_flow(editor):
    """创建持续检测流程"""
    print("创建持续检测流程...")
    
    editor.scene.clear()
    
    # 创建节点
    start = StartEndNode(400, 100, "开始")
    init = SetSignalNode(400, 220)
    duration = DurationNode(400, 360)
    check = CheckSignalNode(400, 500)
    record = SetSignalNode(400, 620)
    analyze = SetSignalNode(400, 740)
    end = StartEndNode(400, 860, "结束")
    
    # 添加到场景
    for node in [start, init, duration, check, record, analyze, end]:
        editor.scene.addItem(node)
    
    # 创建连接
    editor.scene.addItem(ConnectionLine(start, init))
    editor.scene.addItem(ConnectionLine(init, duration))
    editor.scene.addItem(ConnectionLine(duration, check))
    editor.scene.addItem(ConnectionLine(check, record))
    editor.scene.addItem(ConnectionLine(record, check, "loop"))  # 循环
    editor.scene.addItem(ConnectionLine(record, analyze))
    editor.scene.addItem(ConnectionLine(analyze, end))
    
    print("✓ 持续检测流程创建完成")


def main():
    """主函数"""
    print("=" * 60)
    print("PyQt6流程图编辑器 - 快速入门示例")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 创建编辑器
    editor = FlowchartEditor()
    editor.setWindowTitle("快速入门示例 - 信号流程图")
    
    # 选择要创建的流程（取消注释来切换）
    # create_basic_signal_flow(editor)        # 示例1：基础流程
    # create_timeout_flow(editor)             # 示例2：超时控制
    create_async_parallel_flow(editor)      # 示例3：异步并行
    # create_duration_check_flow(editor)      # 示例4：持续检测
    
    print("\n使用说明:")
    print("- 拖动节点可以移动位置")
    print("- 点击工具栏'连接节点'按钮，然后依次点击两个节点创建连接")
    print("- 右键点击节点可以删除")
    print("- 使用左侧工具箱可以添加新节点")
    print("- 使用放大/缩小按钮调整视图")
    print("\n提示：修改main()函数中的注释来切换不同示例")
    print("=" * 60)
    
    editor.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
