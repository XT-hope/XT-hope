"""
PyQt6流程图编辑器
支持: Set Signal, Check Signal, Wait, Timeout, Duration, Async
"""

from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                              QGraphicsScene, QGraphicsItem, QGraphicsTextItem,
                              QToolBar, QGraphicsEllipseItem, QGraphicsRectItem,
                              QGraphicsPolygonItem, QGraphicsLineItem, QMenu,
                              QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QDockWidget, QListWidget)
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF
from PyQt6.QtGui import (QPen, QBrush, QColor, QPainter, QPainterPath, 
                         QPolygonF, QFont, QAction)
import sys


class NodeType:
    """节点类型枚举"""
    SET_SIGNAL = "Set Signal"
    CHECK_SIGNAL = "Check Signal"
    WAIT = "Wait"
    TIMEOUT = "Timeout"
    DURATION = "Duration"
    ASYNC_TASK = "Async Task"
    DECISION = "Decision"
    START_END = "Start/End"
    PROCESS = "Process"


class FlowchartNode(QGraphicsItem):
    """流程图节点基类"""
    
    def __init__(self, node_type, text, x, y, width=120, height=60):
        super().__init__()
        self.node_type = node_type
        self.text = text
        self.width = width
        self.height = height
        self.setPos(x, y)
        
        # 设置标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        # 连接点
        self.connections = []
        
        # 根据节点类型设置颜色
        self.colors = {
            NodeType.SET_SIGNAL: QColor(144, 238, 144),      # 浅绿色
            NodeType.CHECK_SIGNAL: QColor(135, 206, 235),    # 天蓝色
            NodeType.WAIT: QColor(255, 215, 0),              # 金黄色
            NodeType.TIMEOUT: QColor(255, 165, 0),           # 橙色
            NodeType.DURATION: QColor(221, 160, 221),        # 梅红色
            NodeType.ASYNC_TASK: QColor(64, 224, 208),       # 青绿色
            NodeType.DECISION: QColor(211, 211, 211),        # 灰色
            NodeType.START_END: QColor(112, 128, 144),       # 深灰色
            NodeType.PROCESS: QColor(255, 255, 255),         # 白色
        }
        
    def boundingRect(self):
        return QRectF(-self.width/2, -self.height/2, self.width, self.height)
    
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 选中时显示边框
        if self.isSelected():
            pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
        else:
            pen = QPen(QColor(0, 0, 0), 2)
        
        painter.setPen(pen)
        
        # 根据节点类型绘制不同形状
        color = self.colors.get(self.node_type, QColor(255, 255, 255))
        brush = QBrush(color)
        painter.setBrush(brush)
        
        self._draw_shape(painter)
        
        # 绘制文字
        painter.setPen(QColor(0, 0, 0))
        font = QFont("Arial", 10)
        painter.setFont(font)
        painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self.text)
    
    def _draw_shape(self, painter):
        """绘制节点形状（子类重写）"""
        rect = self.boundingRect()
        painter.drawRoundedRect(rect, 10, 10)
    
    def itemChange(self, change, value):
        """节点移动时更新连接线"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            for connection in self.connections:
                connection.update_position()
        return super().itemChange(change, value)
    
    def get_center(self):
        """获取节点中心点"""
        return self.scenePos()
    
    def add_connection(self, connection):
        """添加连接"""
        self.connections.append(connection)
    
    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu()
        delete_action = menu.addAction("删除节点")
        edit_action = menu.addAction("编辑节点")
        
        action = menu.exec(event.screenPos())
        if action == delete_action:
            self.scene().removeItem(self)


class SetSignalNode(FlowchartNode):
    """Set Signal节点 - 圆角矩形"""
    def __init__(self, x, y):
        super().__init__(NodeType.SET_SIGNAL, "Set Signal", x, y)
    
    def _draw_shape(self, painter):
        rect = self.boundingRect()
        painter.drawRoundedRect(rect, 15, 15)


class CheckSignalNode(FlowchartNode):
    """Check Signal节点 - 菱形"""
    def __init__(self, x, y):
        super().__init__(NodeType.CHECK_SIGNAL, "Check Signal", x, y)
    
    def _draw_shape(self, painter):
        polygon = QPolygonF([
            QPointF(0, -self.height/2),          # 上
            QPointF(self.width/2, 0),            # 右
            QPointF(0, self.height/2),           # 下
            QPointF(-self.width/2, 0),           # 左
        ])
        painter.drawPolygon(polygon)


class WaitNode(FlowchartNode):
    """Wait节点 - 平行四边形"""
    def __init__(self, x, y):
        super().__init__(NodeType.WAIT, "Wait\n延迟", x, y)
    
    def _draw_shape(self, painter):
        offset = 15
        polygon = QPolygonF([
            QPointF(-self.width/2 + offset, -self.height/2),  # 左上
            QPointF(self.width/2 + offset, -self.height/2),   # 右上
            QPointF(self.width/2 - offset, self.height/2),    # 右下
            QPointF(-self.width/2 - offset, self.height/2),   # 左下
        ])
        painter.drawPolygon(polygon)


class TimeoutNode(FlowchartNode):
    """Timeout节点 - 六边形"""
    def __init__(self, x, y):
        super().__init__(NodeType.TIMEOUT, "Timeout\n超时控制", x, y, 140, 70)
    
    def _draw_shape(self, painter):
        offset = 20
        polygon = QPolygonF([
            QPointF(-self.width/2 + offset, -self.height/2),  # 左上
            QPointF(self.width/2 - offset, -self.height/2),   # 右上
            QPointF(self.width/2, 0),                         # 右中
            QPointF(self.width/2 - offset, self.height/2),    # 右下
            QPointF(-self.width/2 + offset, self.height/2),   # 左下
            QPointF(-self.width/2, 0),                        # 左中
        ])
        painter.drawPolygon(polygon)


class DurationNode(FlowchartNode):
    """Duration节点 - 双线矩形"""
    def __init__(self, x, y):
        super().__init__(NodeType.DURATION, "Duration\n持续检测", x, y, 140, 70)
    
    def _draw_shape(self, painter):
        rect = self.boundingRect()
        # 外框
        painter.drawRect(rect)
        # 内框
        inner_rect = rect.adjusted(5, 5, -5, -5)
        painter.drawRect(inner_rect)


class AsyncTaskNode(FlowchartNode):
    """Async Task节点 - 圆柱体"""
    def __init__(self, x, y):
        super().__init__(NodeType.ASYNC_TASK, "Async\nTask", x, y, 100, 80)
    
    def _draw_shape(self, painter):
        ellipse_height = 20
        rect_height = self.height - ellipse_height
        
        # 绘制圆柱体身体
        body_rect = QRectF(-self.width/2, -self.height/2 + ellipse_height/2, 
                          self.width, rect_height)
        painter.drawRect(body_rect)
        
        # 绘制顶部椭圆
        top_ellipse = QRectF(-self.width/2, -self.height/2, 
                            self.width, ellipse_height)
        painter.drawEllipse(top_ellipse)
        
        # 绘制底部弧线
        bottom_arc = QRectF(-self.width/2, self.height/2 - ellipse_height, 
                           self.width, ellipse_height)
        painter.drawArc(bottom_arc, 0, 180 * 16)


class DecisionNode(FlowchartNode):
    """Decision节点 - 菱形"""
    def __init__(self, x, y):
        super().__init__(NodeType.DECISION, "判断", x, y)
    
    def _draw_shape(self, painter):
        polygon = QPolygonF([
            QPointF(0, -self.height/2),
            QPointF(self.width/2, 0),
            QPointF(0, self.height/2),
            QPointF(-self.width/2, 0),
        ])
        painter.drawPolygon(polygon)


class StartEndNode(FlowchartNode):
    """Start/End节点 - 椭圆"""
    def __init__(self, x, y, text="开始"):
        super().__init__(NodeType.START_END, text, x, y, 100, 60)
    
    def _draw_shape(self, painter):
        rect = self.boundingRect()
        painter.drawEllipse(rect)


class ConnectionLine(QGraphicsLineItem):
    """连接线"""
    
    def __init__(self, start_node, end_node, line_type="normal"):
        super().__init__()
        self.start_node = start_node
        self.end_node = end_node
        self.line_type = line_type  # normal, timeout, async, loop
        
        # 设置线条样式
        if line_type == "timeout":
            pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
        elif line_type == "async":
            pen = QPen(QColor(0, 128, 255), 3)
        elif line_type == "loop":
            pen = QPen(QColor(128, 128, 128), 2, Qt.PenStyle.DotLine)
        else:
            pen = QPen(QColor(0, 0, 0), 2)
        
        self.setPen(pen)
        self.setZValue(-1)  # 确保线条在节点下方
        
        # 添加箭头
        self.arrow_size = 10
        
        # 注册到节点
        start_node.add_connection(self)
        end_node.add_connection(self)
        
        self.update_position()
    
    def update_position(self):
        """更新连接线位置"""
        start = self.start_node.get_center()
        end = self.end_node.get_center()
        
        line = QLineF(start, end)
        self.setLine(line)
    
    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        
        # 绘制箭头
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.pen())
        painter.setBrush(QBrush(self.pen().color()))
        
        line = self.line()
        angle = line.angle() * 3.14159 / 180
        
        end_point = line.p2()
        arrow_p1 = end_point - QPointF(
            self.arrow_size * (line.dx() / line.length() + 0.5 * (-line.dy() / line.length())),
            self.arrow_size * (line.dy() / line.length() + 0.5 * (line.dx() / line.length()))
        )
        arrow_p2 = end_point - QPointF(
            self.arrow_size * (line.dx() / line.length() - 0.5 * (-line.dy() / line.length())),
            self.arrow_size * (line.dy() / line.length() - 0.5 * (line.dx() / line.length()))
        )
        
        arrow_head = QPolygonF([end_point, arrow_p1, arrow_p2])
        painter.drawPolygon(arrow_head)


class FlowchartScene(QGraphicsScene):
    """流程图场景"""
    
    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2000, 2000)
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250)))
        
        # 连接模式
        self.connection_mode = False
        self.connection_start_node = None
        self.temp_line = None
    
    def start_connection(self):
        """开始连接模式"""
        self.connection_mode = True
        self.connection_start_node = None
    
    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if self.connection_mode:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(item, FlowchartNode):
                if self.connection_start_node is None:
                    self.connection_start_node = item
                else:
                    # 创建连接
                    connection = ConnectionLine(self.connection_start_node, item)
                    self.addItem(connection)
                    self.connection_mode = False
                    self.connection_start_node = None
        else:
            super().mousePressEvent(event)


class FlowchartEditor(QMainWindow):
    """流程图编辑器主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("流程图编辑器 - Signal Flow Control")
        self.setGeometry(100, 100, 1400, 900)
        
        # 创建场景和视图
        self.scene = FlowchartScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        self.setCentralWidget(self.view)
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建节点面板
        self.create_node_panel()
        
        # 添加示例流程图
        self.create_example_flowchart()
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("工具")
        self.addToolBar(toolbar)
        
        # 连接按钮
        connect_action = QAction("连接节点", self)
        connect_action.triggered.connect(self.start_connection)
        toolbar.addAction(connect_action)
        
        toolbar.addSeparator()
        
        # 缩放按钮
        zoom_in_action = QAction("放大", self)
        zoom_in_action.triggered.connect(lambda: self.view.scale(1.2, 1.2))
        toolbar.addAction(zoom_in_action)
        
        zoom_out_action = QAction("缩小", self)
        zoom_out_action.triggered.connect(lambda: self.view.scale(0.8, 0.8))
        toolbar.addAction(zoom_out_action)
        
        toolbar.addSeparator()
        
        # 清空按钮
        clear_action = QAction("清空画布", self)
        clear_action.triggered.connect(self.clear_scene)
        toolbar.addAction(clear_action)
    
    def create_node_panel(self):
        """创建节点面板"""
        dock = QDockWidget("节点工具箱", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | 
                            Qt.DockWidgetArea.RightDockWidgetArea)
        
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 添加节点按钮
        nodes = [
            ("Set Signal", self.add_set_signal_node),
            ("Check Signal", self.add_check_signal_node),
            ("Wait", self.add_wait_node),
            ("Timeout", self.add_timeout_node),
            ("Duration", self.add_duration_node),
            ("Async Task", self.add_async_task_node),
            ("Decision", self.add_decision_node),
            ("Start/End", self.add_start_end_node),
        ]
        
        layout.addWidget(QLabel("点击添加节点:"))
        
        for name, func in nodes:
            btn = QPushButton(name)
            btn.clicked.connect(func)
            layout.addWidget(btn)
        
        layout.addStretch()
        widget.setLayout(layout)
        dock.setWidget(widget)
        
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    
    def add_set_signal_node(self):
        """添加Set Signal节点"""
        node = SetSignalNode(200, 200)
        self.scene.addItem(node)
    
    def add_check_signal_node(self):
        """添加Check Signal节点"""
        node = CheckSignalNode(200, 200)
        self.scene.addItem(node)
    
    def add_wait_node(self):
        """添加Wait节点"""
        node = WaitNode(200, 200)
        self.scene.addItem(node)
    
    def add_timeout_node(self):
        """添加Timeout节点"""
        node = TimeoutNode(200, 200)
        self.scene.addItem(node)
    
    def add_duration_node(self):
        """添加Duration节点"""
        node = DurationNode(200, 200)
        self.scene.addItem(node)
    
    def add_async_task_node(self):
        """添加Async Task节点"""
        node = AsyncTaskNode(200, 200)
        self.scene.addItem(node)
    
    def add_decision_node(self):
        """添加Decision节点"""
        node = DecisionNode(200, 200)
        self.scene.addItem(node)
    
    def add_start_end_node(self):
        """添加Start/End节点"""
        node = StartEndNode(200, 200, "开始")
        self.scene.addItem(node)
    
    def start_connection(self):
        """开始连接模式"""
        self.scene.start_connection()
    
    def clear_scene(self):
        """清空场景"""
        self.scene.clear()
    
    def create_example_flowchart(self):
        """创建示例流程图"""
        # 开始节点
        start = StartEndNode(400, 100, "开始")
        self.scene.addItem(start)
        
        # Set Signal节点
        set_signal = SetSignalNode(400, 220)
        self.scene.addItem(set_signal)
        
        # Wait节点
        wait = WaitNode(400, 340)
        self.scene.addItem(wait)
        
        # Timeout节点（侧边）
        timeout = TimeoutNode(600, 340)
        self.scene.addItem(timeout)
        
        # Check Signal节点
        check = CheckSignalNode(400, 480)
        self.scene.addItem(check)
        
        # Decision节点
        decision = DecisionNode(400, 620)
        self.scene.addItem(decision)
        
        # Duration节点（示例，右侧）
        duration = DurationNode(750, 480)
        self.scene.addItem(duration)
        
        # Async Task节点（左侧）
        async_task = AsyncTaskNode(150, 480)
        self.scene.addItem(async_task)
        
        # 结束节点
        end = StartEndNode(400, 760, "结束")
        self.scene.addItem(end)
        
        # 创建连接
        self.scene.addItem(ConnectionLine(start, set_signal, "normal"))
        self.scene.addItem(ConnectionLine(set_signal, wait, "normal"))
        self.scene.addItem(ConnectionLine(wait, check, "normal"))
        self.scene.addItem(ConnectionLine(timeout, check, "timeout"))
        self.scene.addItem(ConnectionLine(check, decision, "normal"))
        self.scene.addItem(ConnectionLine(decision, end, "normal"))
        self.scene.addItem(ConnectionLine(async_task, check, "async"))
        self.scene.addItem(ConnectionLine(duration, decision, "normal"))


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    editor = FlowchartEditor()
    editor.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
