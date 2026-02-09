"""
使用Graphviz自动布局的流程图实现
优势：自动布局、专业图形渲染
"""

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                              QVBoxLayout, QPushButton, QLabel, 
                              QTextEdit, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtSvgWidgets import QSvgWidget
import sys

try:
    import graphviz
    GRAPHVIZ_AVAILABLE = True
except ImportError:
    GRAPHVIZ_AVAILABLE = False


class GraphvizFlowchartViewer(QMainWindow):
    """使用Graphviz的流程图查看器"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Graphviz流程图查看器")
        self.setGeometry(100, 100, 1200, 800)
        
        if not GRAPHVIZ_AVAILABLE:
            self.show_error()
            return
        
        # 创建主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：代码编辑器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("DOT代码编辑器:"))
        
        self.code_editor = QTextEdit()
        self.code_editor.setPlaceholderText("在此输入DOT语言代码...")
        left_layout.addWidget(self.code_editor)
        
        # 按钮
        btn_layout = QVBoxLayout()
        
        self.render_btn = QPushButton("渲染流程图")
        self.render_btn.clicked.connect(self.render_flowchart)
        btn_layout.addWidget(self.render_btn)
        
        self.example1_btn = QPushButton("示例1: 基础信号检测")
        self.example1_btn.clicked.connect(self.load_example1)
        btn_layout.addWidget(self.example1_btn)
        
        self.example2_btn = QPushButton("示例2: 持续检测")
        self.example2_btn.clicked.connect(self.load_example2)
        btn_layout.addWidget(self.example2_btn)
        
        self.example3_btn = QPushButton("示例3: 异步并行")
        self.example3_btn.clicked.connect(self.load_example3)
        btn_layout.addWidget(self.example3_btn)
        
        left_layout.addLayout(btn_layout)
        
        # 右侧：SVG显示
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("流程图预览:"))
        
        self.svg_widget = QSvgWidget()
        right_layout.addWidget(self.svg_widget)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        
        # 加载默认示例
        self.load_example1()
    
    def show_error(self):
        """显示错误信息"""
        label = QLabel("请先安装graphviz库:\npip install graphviz\n\n"
                      "并确保系统已安装Graphviz:\n"
                      "Ubuntu: sudo apt install graphviz\n"
                      "macOS: brew install graphviz\n"
                      "Windows: 从 https://graphviz.org/download/ 下载")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)
    
    def render_flowchart(self):
        """渲染流程图"""
        if not GRAPHVIZ_AVAILABLE:
            return
        
        dot_code = self.code_editor.toPlainText()
        
        try:
            # 创建图形
            graph = graphviz.Source(dot_code)
            
            # 渲染为SVG
            svg_data = graph.pipe(format='svg')
            
            # 显示SVG
            self.svg_widget.load(svg_data)
            
        except Exception as e:
            print(f"渲染错误: {e}")
    
    def load_example1(self):
        """加载示例1：基础信号检测流程"""
        dot_code = '''digraph SignalCheck {
    rankdir=TB;
    node [fontname="Arial"];
    
    // 节点定义
    start [label="开始", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    set_signal [label="Set Signal\\nsignal = True", shape=box, style="rounded,filled", fillcolor="#90EE90"];
    wait [label="Wait\\n延迟2s", shape=parallelogram, style=filled, fillcolor="#FFD700"];
    timeout [label="Timeout\\n超时5s", shape=hexagon, style=filled, fillcolor="#FFA500"];
    check [label="Check Signal\\n检查信号", shape=diamond, style=filled, fillcolor="#87CEEB"];
    decision [label="满足条件?", shape=diamond, style=filled, fillcolor="#D3D3D3"];
    success [label="成功返回", shape=box, style="rounded,filled", fillcolor="#32CD32", fontcolor=white];
    timeout_fail [label="超时失败", shape=box, style="rounded,filled", fillcolor="#DC143C", fontcolor=white];
    end_node [label="结束", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    
    // 连接
    start -> set_signal;
    set_signal -> wait;
    wait -> check;
    timeout -> check [style=dashed, color=red, label="监控"];
    check -> decision;
    decision -> success [label="是"];
    decision -> check [label="否\\n未超时", style=dotted];
    decision -> timeout_fail [label="超时"];
    success -> end_node;
    timeout_fail -> end_node;
}'''
        self.code_editor.setText(dot_code)
        self.render_flowchart()
    
    def load_example2(self):
        """加载示例2：持续检测流程"""
        dot_code = '''digraph Duration {
    rankdir=TB;
    node [fontname="Arial"];
    
    start [label="开始检测", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    init [label="初始化\\nduration=10s\\ninterval=0.1s", shape=box, style=filled, fillcolor="#90EE90"];
    duration [label="Duration\\n启动持续检测", shape=box, style="filled", fillcolor="#DDA0DD", peripheries=2];
    loop [label="循环检查", shape=box, style=filled, fillcolor="#E0E0E0"];
    check [label="Check Signal\\n检查信号", shape=diamond, style=filled, fillcolor="#87CEEB"];
    record [label="记录结果", shape=box, style=filled, fillcolor="#F0F0F0"];
    time_check [label="时间到?", shape=diamond, style=filled, fillcolor="#D3D3D3"];
    analyze [label="统计分析\\n计算成功率", shape=box, style=filled, fillcolor="#FFA500"];
    output [label="输出结果", shape=box, style="rounded,filled", fillcolor="#32CD32", fontcolor=white];
    end_node [label="结束", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    
    start -> init;
    init -> duration;
    duration -> loop;
    loop -> check;
    check -> record;
    record -> time_check;
    time_check -> loop [label="否\\n等待interval", style=dotted];
    time_check -> analyze [label="是"];
    analyze -> output;
    output -> end_node;
}'''
        self.code_editor.setText(dot_code)
        self.render_flowchart()
    
    def load_example3(self):
        """加载示例3：异步并行流程"""
        dot_code = '''digraph Async {
    rankdir=TB;
    node [fontname="Arial"];
    
    start [label="主流程开始", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    create_tasks [label="创建异步任务组", shape=box, style="rounded,filled", fillcolor="#90EE90"];
    
    // 任务1
    task1 [label="Async Task 1", shape=cylinder, style=filled, fillcolor="#40E0D0"];
    set1 [label="Set Signal A", shape=box, style=filled, fillcolor="#90EE90"];
    check1 [label="Check A", shape=diamond, style=filled, fillcolor="#87CEEB"];
    
    // 任务2
    task2 [label="Async Task 2", shape=cylinder, style=filled, fillcolor="#40E0D0"];
    set2 [label="Set Signal B", shape=box, style=filled, fillcolor="#90EE90"];
    check2 [label="Check B", shape=diamond, style=filled, fillcolor="#87CEEB"];
    
    // 任务3
    task3 [label="Async Task 3", shape=cylinder, style=filled, fillcolor="#40E0D0"];
    wait3 [label="Wait 2s", shape=parallelogram, style=filled, fillcolor="#FFD700"];
    check3 [label="Check C", shape=diamond, style=filled, fillcolor="#87CEEB"];
    
    // 汇总
    timeout [label="Global Timeout\\n15s", shape=hexagon, style=filled, fillcolor="#FFA500"];
    wait_all [label="等待所有任务", shape=box, style=filled, fillcolor="#E0E0E0"];
    collect [label="汇总结果", shape=box, style=filled, fillcolor="#FFA500"];
    result [label="分析结果", shape=diamond, style=filled, fillcolor="#D3D3D3"];
    success [label="全部成功", shape=box, style="rounded,filled", fillcolor="#32CD32", fontcolor=white];
    partial [label="部分成功", shape=box, style="rounded,filled", fillcolor="#FFA500"];
    fail [label="失败", shape=box, style="rounded,filled", fillcolor="#DC143C", fontcolor=white];
    end_node [label="结束", shape=ellipse, style=filled, fillcolor="#708090", fontcolor=white];
    
    // 连接
    start -> create_tasks;
    
    create_tasks -> task1;
    create_tasks -> task2;
    create_tasks -> task3;
    
    task1 -> set1 -> check1;
    task2 -> set2 -> check2;
    task3 -> wait3 -> check3;
    
    check1 -> wait_all;
    check2 -> wait_all;
    check3 -> wait_all;
    
    timeout -> wait_all [style=dashed, color=red];
    wait_all -> collect;
    collect -> result;
    
    result -> success [label="全部成功"];
    result -> partial [label="部分失败"];
    result -> fail [label="全部失败"];
    
    success -> end_node;
    partial -> end_node;
    fail -> end_node;
    
    // 设置并行布局
    {rank=same; task1; task2; task3;}
    {rank=same; set1; set2; wait3;}
    {rank=same; check1; check2; check3;}
}'''
        self.code_editor.setText(dot_code)
        self.render_flowchart()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    viewer = GraphvizFlowchartViewer()
    viewer.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
