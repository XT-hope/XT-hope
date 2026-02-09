"""
使用pyqtgraph创建流程图
优势：高性能、适合数据流程图
"""

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                              QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QSplitter)
from PyQt6.QtCore import Qt
import sys

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class PyQtGraphFlowchart(QMainWindow):
    """使用pyqtgraph的流程图编辑器"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQtGraph流程图")
        self.setGeometry(100, 100, 1400, 900)
        
        if not PYQTGRAPH_AVAILABLE:
            self.show_error()
            return
        
        # 创建主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 标题
        title = QLabel("PyQtGraph流程图 - 数据流可视化")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # 创建flowchart
        self.fc = pg.flowchart.Flowchart(terminals={})
        layout.addWidget(self.fc.widget())
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        
        example1_btn = QPushButton("示例1: 信号处理流程")
        example1_btn.clicked.connect(self.create_signal_flow)
        btn_layout.addWidget(example1_btn)
        
        example2_btn = QPushButton("示例2: 数据采集与检测")
        example2_btn.clicked.connect(self.create_data_flow)
        btn_layout.addWidget(example2_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear_flowchart)
        btn_layout.addWidget(clear_btn)
        
        layout.addLayout(btn_layout)
        
        # 说明文本
        info = QLabel(
            "说明: 使用pyqtgraph的flowchart模块创建数据流图\n"
            "- 拖动节点可以移动位置\n"
            "- 点击节点可以查看和编辑参数\n"
            "- 连接端点创建数据流连接"
        )
        info.setStyleSheet("background-color: #F0F0F0; padding: 10px; border-radius: 5px;")
        layout.addWidget(info)
        
        # 加载默认示例
        self.create_signal_flow()
    
    def show_error(self):
        """显示错误信息"""
        label = QLabel("请先安装pyqtgraph库:\npip install pyqtgraph")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 16px;")
        self.setCentralWidget(label)
    
    def clear_flowchart(self):
        """清空流程图"""
        self.fc.clear()
    
    def create_signal_flow(self):
        """创建信号处理流程"""
        self.clear_flowchart()
        
        # 创建节点
        # 输入节点
        input_node = self.fc.createNode('Input', pos=(0, 0))
        
        # 信号设置节点
        set_signal = self.fc.createNode('Function', pos=(150, 0))
        set_signal.setName('SetSignal')
        
        # 延迟节点
        wait_node = self.fc.createNode('Delay', pos=(300, 0))
        wait_node.setName('Wait')
        
        # 检查节点
        check_node = self.fc.createNode('Function', pos=(450, 0))
        check_node.setName('CheckSignal')
        
        # 判断节点（使用Filter代替）
        decision_node = self.fc.createNode('Filter', pos=(600, 0))
        decision_node.setName('Decision')
        
        # 输出节点
        output_node = self.fc.createNode('Output', pos=(750, 0))
        
        # 创建连接
        self.fc.connectTerminals(input_node['dataOut'], set_signal['dataIn'])
        self.fc.connectTerminals(set_signal['dataOut'], wait_node['dataIn'])
        self.fc.connectTerminals(wait_node['dataOut'], check_node['dataIn'])
        self.fc.connectTerminals(check_node['dataOut'], decision_node['dataIn'])
        self.fc.connectTerminals(decision_node['dataOut'], output_node['dataIn'])
    
    def create_data_flow(self):
        """创建数据采集与检测流程"""
        self.clear_flowchart()
        
        # 创建多个输入源
        input1 = self.fc.createNode('Input', pos=(0, -100))
        input1.setName('Sensor_A')
        
        input2 = self.fc.createNode('Input', pos=(0, 0))
        input2.setName('Sensor_B')
        
        input3 = self.fc.createNode('Input', pos=(0, 100))
        input3.setName('Sensor_C')
        
        # 处理节点
        process1 = self.fc.createNode('Function', pos=(200, -100))
        process1.setName('Process_A')
        
        process2 = self.fc.createNode('Function', pos=(200, 0))
        process2.setName('Process_B')
        
        process3 = self.fc.createNode('Function', pos=(200, 100))
        process3.setName('Process_C')
        
        # 合并节点
        merge = self.fc.createNode('Function', pos=(400, 0))
        merge.setName('Merge')
        
        # 检测节点
        check = self.fc.createNode('Filter', pos=(550, 0))
        check.setName('Check')
        
        # 输出
        output = self.fc.createNode('Output', pos=(700, 0))
        
        # 创建连接
        self.fc.connectTerminals(input1['dataOut'], process1['dataIn'])
        self.fc.connectTerminals(input2['dataOut'], process2['dataIn'])
        self.fc.connectTerminals(input3['dataOut'], process3['dataIn'])
        
        self.fc.connectTerminals(process1['dataOut'], merge['dataIn'])
        self.fc.connectTerminals(process2['dataOut'], merge['dataIn'])
        self.fc.connectTerminals(process3['dataOut'], merge['dataIn'])
        
        self.fc.connectTerminals(merge['dataOut'], check['dataIn'])
        self.fc.connectTerminals(check['dataOut'], output['dataIn'])


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    viewer = PyQtGraphFlowchart()
    viewer.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
