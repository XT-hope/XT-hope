"""
Qt6 悬浮可移动 AI 提示按钮示例
功能：
1. 无边框悬浮窗口
2. 可拖动移动
3. 始终置顶
4. 点击显示 AI 提示弹窗
"""

from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, 
                              QLabel, QTextEdit, QDialog, QHBoxLayout)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon, QPalette, QColor
import sys


class DraggableButton(QPushButton):
    """可拖动的按钮类"""
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.dragging = False
        self.drag_position = QPoint()
        self.click_position = QPoint()
        self.moved = False  # 标记是否发生了移动
        
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.click_position = event.pos()
            self.drag_position = event.globalPosition().toPoint() - self.window().pos()
            self.moved = False
            event.accept()
            
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.dragging:
            # 计算移动距离，判断是否真的在拖动
            move_distance = (event.pos() - self.click_position).manhattanLength()
            if move_distance > 5:  # 移动超过5像素才算拖动
                self.moved = True
                new_pos = event.globalPosition().toPoint() - self.drag_position
                self.window().move(new_pos)
            event.accept()
            
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            # 只有在没有发生拖动时才触发点击事件
            if not self.moved:
                super().mouseReleaseEvent(event)
            event.accept()


class FloatingButton(QWidget):
    """悬浮可移动按钮"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        # 设置窗口属性
        # Qt.WindowType.FramelessWindowHint: 无边框窗口
        # Qt.WindowType.WindowStaysOnTopHint: 窗口置顶
        # Qt.WindowType.Tool: 工具窗口（不显示在任务栏）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        
        # 设置窗口透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 创建主按钮 - 使用可拖动按钮
        self.main_button = DraggableButton('AI')
        self.main_button.setFixedSize(60, 60)
        self.main_button.clicked.connect(self.show_ai_dialog)
        
        # 设置按钮样式 - 圆形、渐变、阴影效果
        self.main_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border-radius: 30px;
                font-size: 18px;
                font-weight: bold;
                border: 3px solid white;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #764ba2, stop:1 #667eea);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5568d3, stop:1 #6a3f92);
            }
        """)
        
        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.main_button)
        layout.setContentsMargins(5, 5, 5, 5)  # 添加外边距以显示阴影效果
        self.setLayout(layout)
        
        # 设置窗口大小
        self.resize(70, 70)
        
        # 设置初始位置（屏幕右下角）
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 100, screen.height() - 150)
            
    def show_ai_dialog(self):
        """显示 AI 提示对话框"""
        dialog = AIPromptDialog(self)
        dialog.exec()


class AIPromptDialog(QDialog):
    """AI 提示对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """初始化对话框界面"""
        self.setWindowTitle('AI 助手')
        self.setMinimumSize(400, 300)
        
        # 创建布局
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel('AI 智能助手')
        title.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #667eea;
                padding: 10px;
            }
        """)
        layout.addWidget(title)
        
        # 提示信息
        info_label = QLabel('请输入您的问题或需要帮助的内容：')
        info_label.setStyleSheet("padding: 5px;")
        layout.addWidget(info_label)
        
        # 输入框
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText('例如：帮我优化这段代码...')
        self.input_text.setStyleSheet("""
            QTextEdit {
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 2px solid #667eea;
            }
        """)
        layout.addWidget(self.input_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 发送按钮
        send_button = QPushButton('发送')
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5568d3;
            }
            QPushButton:pressed {
                background-color: #4a5ac0;
            }
        """)
        send_button.clicked.connect(self.send_message)
        
        # 取消按钮
        cancel_button = QPushButton('取消')
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                border: none;
                border-radius: 5px;
                padding: 10px 30px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(send_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def send_message(self):
        """发送消息（这里可以集成实际的 AI API）"""
        message = self.input_text.toPlainText()
        if message.strip():
            # 这里可以添加实际的 AI API 调用
            print(f"发送给 AI: {message}")
            self.accept()
        else:
            self.input_text.setFocus()


class AdvancedFloatingButton(QWidget):
    """高级悬浮按钮 - 带有展开菜单"""
    
    def __init__(self):
        super().__init__()
        self.expanded = False
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        # 设置窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 创建布局
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # 主按钮 - 使用可拖动按钮
        self.main_button = DraggableButton('AI')
        self.main_button.setFixedSize(60, 60)
        self.main_button.clicked.connect(self.toggle_menu)
        self.main_button.setStyleSheet(self.get_button_style('#667eea', '#764ba2'))
        self.layout.addWidget(self.main_button)
        
        # 功能按钮（初始隐藏）- 使用可拖动按钮
        self.chat_button = self.create_menu_button('对话', '#f093fb', '#f5576c')
        self.code_button = self.create_menu_button('代码', '#4facfe', '#00f2fe')
        self.help_button = self.create_menu_button('帮助', '#43e97b', '#38f9d7')
        
        # 连接功能按钮事件
        self.chat_button.clicked.connect(lambda: self.show_ai_dialog('对话模式'))
        self.code_button.clicked.connect(lambda: self.show_ai_dialog('代码模式'))
        self.help_button.clicked.connect(lambda: self.show_ai_dialog('帮助模式'))
        
        self.setLayout(self.layout)
        self.resize(70, 70)
        
        # 设置初始位置
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 100, screen.height() - 150)
        
    def create_menu_button(self, text, color1, color2):
        """创建菜单按钮"""
        button = DraggableButton(text)
        button.setFixedSize(60, 60)
        button.setStyleSheet(self.get_button_style(color1, color2))
        button.hide()  # 初始隐藏
        self.layout.addWidget(button)
        return button
        
    def get_button_style(self, color1, color2):
        """获取按钮样式"""
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {color1}, stop:1 {color2});
                color: white;
                border-radius: 30px;
                font-size: 14px;
                font-weight: bold;
                border: 3px solid white;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {color2}, stop:1 {color1});
            }}
        """
        
    def toggle_menu(self):
        """切换菜单显示/隐藏"""
        if self.expanded:
            # 收起菜单
            self.chat_button.hide()
            self.code_button.hide()
            self.help_button.hide()
            self.resize(70, 70)
        else:
            # 展开菜单
            self.chat_button.show()
            self.code_button.show()
            self.help_button.show()
            self.resize(70, 280)
        self.expanded = not self.expanded
            
    def show_ai_dialog(self, mode):
        """显示 AI 对话框"""
        dialog = AIPromptDialog(self)
        dialog.setWindowTitle(f'AI 助手 - {mode}')
        dialog.exec()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建简单版悬浮按钮
    # simple_button = FloatingButton()
    # simple_button.show()
    
    # 创建高级版悬浮按钮（带展开菜单）
    advanced_button = AdvancedFloatingButton()
    advanced_button.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
