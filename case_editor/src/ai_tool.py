"""
Qt6 悬浮可移动 AI 提示按钮示例（修复窗口置顶问题）
修复：只有悬浮按钮置顶，其他窗口正常显示
"""

import json
import os
import sys
from datetime import datetime

import requests
from PyQt6.QtCore import QPoint, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AIAPIThread(QThread):
    """AI API 调用线程"""

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    config_saved = pyqtSignal(str)  # 配置保存成功信号

    def __init__(self, api_config, messages):
        super().__init__()
        self.api_config = api_config
        self.messages = messages

    def run(self):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_config['api_key']}",
            }

            data = {
                "model": self.api_config["model"],
                "messages": self.messages,
                "max_tokens": self.api_config["max_tokens"],
                "temperature": 0.7,
            }

            response = requests.post(
                f"{self.api_config['base_url']}/chat/completions",
                headers=headers,
                json=data,
                timeout=self.api_config["timeout"],
            )

            if response.status_code == 200:
                result = response.json()
                ai_message = result["choices"][0]["message"]["content"]
                self.response_ready.emit(ai_message)
            else:
                error_msg = f"API 错误 {response.status_code}: {response.text}"
                self.error_occurred.emit(error_msg)

        except requests.Timeout:
            self.error_occurred.emit("请求超时，请检查网络连接或增加超时时间")
        except requests.ConnectionError:
            self.error_occurred.emit("连接错误，请检查 Base URL 和网络连接")
        except Exception as e:
            self.error_occurred.emit(f"发生错误: {str(e)}")


class APIConfigDialog(QDialog):
    """API 配置对话框（不置顶，独立窗口）"""

    config_saved = pyqtSignal(str)  # 配置保存成功信号

    def __init__(self, parent=None):
        super().__init__(parent)
        # 关键修复：使用 Window 而不是 Dialog，并且不设置父窗口为置顶的悬浮按钮
        # 这样可以避免继承父窗口的置顶属性
        self.setWindowFlags(
            Qt.WindowType.Window |  # 独立窗口
            Qt.WindowType.FramelessWindowHint  # 无边框
            # 特意不加 WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.config = self.load_config()
        self.dragging = False
        self.drag_position = QPoint()
        self.init_ui()

    def init_ui(self):
        """初始化配置界面"""
        self.setFixedSize(540, 500)

        # 主容器
        main_container = QWidget()
        main_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 10px;
            }
        """)

        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 自定义标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(50)
        title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 10, 0)

        title_label = QLabel("AI API 配置")
        title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }
        """)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.5);
            }
        """)
        close_button.clicked.connect(self.reject)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_button)

        main_layout.addWidget(title_bar)

        # 内容区域
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # 表单
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        # API Key
        key_container = QWidget()
        key_layout = QHBoxLayout(key_container)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(10)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setText(self.config.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setStyleSheet(self.get_input_style())

        show_key_button = QPushButton("显示")
        show_key_button.setFixedWidth(60)
        show_key_button.setCheckable(True)
        show_key_button.toggled.connect(self.toggle_api_key_visibility)
        show_key_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton:checked {
                background-color: #667eea;
                color: white;
                border-color: #667eea;
            }
        """)

        key_layout.addWidget(self.api_key_input)
        key_layout.addWidget(show_key_button)

        form_layout.addRow("API Key:", key_container)

        # Base URL
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1")
        self.base_url_input.setText(self.config.get("base_url", "https://api.openai.com/v1"))
        self.base_url_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Base URL:", self.base_url_input)

        # Model
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("gpt-3.5-turbo")
        self.model_input.setText(self.config.get("model", "gpt-3.5-turbo"))
        self.model_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("模型:", self.model_input)

        # Max Tokens
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(1, 10000000)
        self.max_tokens_input.setValue(self.config.get("max_tokens", 2000))
        self.max_tokens_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("最大 Tokens:", self.max_tokens_input)

        # Timeout
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(5, 300)
        self.timeout_input.setValue(self.config.get("timeout", 30))
        self.timeout_input.setSuffix(" 秒")
        self.timeout_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("超时时间:", self.timeout_input)

        content_layout.addLayout(form_layout)

        # 提示信息
        hint_label = QLabel("提示: 支持 OpenAI API 及兼容接口")
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 10px 0;")
        hint_label.setWordWrap(True)
        content_layout.addWidget(hint_label)

        content_layout.addStretch()

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        test_button = QPushButton("测试连接")
        test_button.setFixedHeight(40)
        test_button.setStyleSheet("""
            QPushButton {
                background-color: #43e97b;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 0px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #38d66d;
            }
        """)
        test_button.clicked.connect(self.test_connection)

        cancel_button = QPushButton("取消")
        cancel_button.setFixedHeight(40)
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                border: none;
                border-radius: 5px;
                padding: 0px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
        """)
        cancel_button.clicked.connect(self.reject)

        save_button = QPushButton("保存")
        save_button.setFixedHeight(40)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 0px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5568d3;
            }
        """)
        save_button.clicked.connect(self.save_config)

        button_layout.addWidget(test_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)

        content_layout.addLayout(button_layout)

        main_layout.addWidget(content_widget)

        # 外层布局
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.addWidget(main_container)

        # 添加阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 0)
        main_container.setGraphicsEffect(shadow)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.pos().y() < 50:
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.pos()
                event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False
        event.accept()

    def get_input_style(self):
        return """
            QLineEdit, QSpinBox {
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 2px solid #667eea;
            }
        """

    def toggle_api_key_visibility(self, checked):
        if checked:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def test_connection(self):
        config = self.get_current_config()

        if not config["api_key"]:
            QMessageBox.warning(self, "警告", "请输入 API Key")
            return

        progress = QProgressDialog("正在测试 API 连接...", "取消", 0, 0, self)
        progress.setWindowTitle("测试中")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
            }

            data = {
                "model": config["model"],
                "messages": [{"role": "user", "content": "测试"}],
                "max_tokens": 10,
            }

            response = requests.post(
                f"{config['base_url']}/chat/completions",
                headers=headers,
                json=data,
                timeout=min(config["timeout"], 10),
            )

            progress.close()
            QApplication.processEvents()

            if response.status_code == 200:
                QMessageBox.information(self, "成功", "API 连接测试成功！")
            else:
                QMessageBox.warning(
                    self,
                    "失败",
                    f"API 返回错误 {response.status_code}:\n{response.text[:200]}",
                )

        except Exception as e:
            progress.close()
            QApplication.processEvents()
            QMessageBox.critical(self, "错误", f"连接失败:\n{str(e)}")

    def get_current_config(self):
        return {
            "api_key": self.api_key_input.text().strip(),
            "base_url": self.base_url_input.text().strip().rstrip("/"),
            "model": self.model_input.text().strip(),
            "max_tokens": self.max_tokens_input.value(),
            "timeout": self.timeout_input.value(),
        }

    def save_config(self):
        config = self.get_current_config()

        if not config["api_key"]:
            QMessageBox.warning(self, "警告", "请输入 API Key")
            return

        config_path = os.path.expanduser("~/.ai_assistant_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            self.config = config
            # 发送配置保存成功信号，而不是弹窗
            self.config_saved.emit("AI API配置成功")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败:\n{str(e)}")

    def load_config(self):
        config_path = os.path.expanduser("~/.ai_assistant_config.json")
        default_config = {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo",
            "max_tokens": 2000,
            "timeout": 30,
        }

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default_config

        return default_config


class DraggableButton(QPushButton):
    """可拖动的按钮类"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.dragging = False
        self.drag_position = QPoint()
        self.click_position = QPoint()
        self.moved = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.click_position = event.pos()
            self.drag_position = event.globalPosition().toPoint() - self.window().pos()
            self.moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            move_distance = (event.pos() - self.click_position).manhattanLength()
            if move_distance > 5:
                self.moved = True
                new_pos = event.globalPosition().toPoint() - self.drag_position
                self.window().move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            if not self.moved:
                super().mouseReleaseEvent(event)
            event.accept()


class CloseButton(QPushButton):
    """自定义关闭按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                border: none;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.8);
            }
            QPushButton:pressed {
                background-color: rgba(200, 0, 0, 1);
            }
        """)
        self.setText("×")


class MessageBubble(QWidget):
    """聊天消息气泡"""

    def __init__(self, message, is_user=True, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.message = message
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)

        message_container = QWidget()
        message_container.setMaximumWidth(400)

        if self.is_user:
            message_container.setStyleSheet("""
                QWidget {
                    background-color: #667eea;
                    border-radius: 10px;
                    padding: 10px 15px;
                }
            """)
        else:
            message_container.setStyleSheet("""
                QWidget {
                    background-color: #f0f0f0;
                    border-radius: 10px;
                    padding: 10px 15px;
                }
            """)

        message_layout = QVBoxLayout(message_container)
        message_layout.setContentsMargins(5, 5, 5, 5)
        message_layout.setSpacing(5)

        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if self.is_user:
            message_label.setStyleSheet("color: white; font-size: 14px;")
        else:
            message_label.setStyleSheet("color: #333; font-size: 14px;")

        message_layout.addWidget(message_label)

        time_label = QLabel(datetime.now().strftime("%H:%M"))
        if self.is_user:
            time_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 11px;")
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            time_label.setStyleSheet("color: rgba(0, 0, 0, 0.5); font-size: 11px;")
            time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        message_layout.addWidget(time_label)

        if self.is_user:
            layout.addStretch()
            layout.addWidget(message_container)
        else:
            layout.addWidget(message_container)
            layout.addStretch()

        self.setLayout(layout)


class ChatAIDialog(QDialog):
    """AI 聊天对话框（不置顶，独立窗口）"""

    def __init__(self, parent=None):
        super().__init__(None)  # 关键修复：不设置父窗口，避免继承置顶属性

        # 使用独立窗口，不置顶
        self.setWindowFlags(
            Qt.WindowType.Window |  # 独立窗口
            Qt.WindowType.FramelessWindowHint  # 无边框
            # 特意不加 WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.dragging = False
        self.drag_position = QPoint()
        self.messages = []
        self.api_config = self.load_api_config()
        self.api_thread = None
        self.init_ui()

        self.add_ai_message("您好！我是 AI 智能助手，有什么可以帮助您的吗？")

    def load_api_config(self):
        config_path = os.path.expanduser("~/.ai_assistant_config.json")
        default_config = {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo",
            "max_tokens": 2000,
            "timeout": 30,
        }

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default_config

        return default_config

    def init_ui(self):
        self.setMinimumSize(500, 600)
        self.resize(500, 600)

        main_container = QWidget()
        main_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 10px;
            }
        """)

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(50)
        title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)

        self.title_label = QLabel("AI 智能助手")
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }
        """)

        self.status_label = QLabel("● 在线")
        self.status_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.9);
                font-size: 12px;
                background: transparent;
            }
        """)

        settings_button = QPushButton("⚙")
        settings_button.setFixedSize(30, 30)
        settings_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 20px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        settings_button.clicked.connect(self.show_settings)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.5);
            }
        """)
        close_button.clicked.connect(self.close)

        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.status_label)
        title_layout.addStretch()
        title_layout.addWidget(settings_button)
        title_layout.addWidget(close_button)

        container_layout.addWidget(title_bar)

        # 聊天区域
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #fafafa;
            }
            QScrollBar:vertical {
                border: none;
                background: #f0f0f0;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #c0c0c0;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a0a0a0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()

        chat_scroll.setWidget(self.messages_widget)
        container_layout.addWidget(chat_scroll)

        # 输入区域
        input_container = QWidget()
        input_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }
        """)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(15, 10, 15, 15)
        input_layout.setSpacing(10)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("输入消息...")
        self.input_text.setMaximumHeight(80)
        self.input_text.setStyleSheet("""
            QTextEdit {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
                background-color: white;
            }
            QTextEdit:focus {
                border: 2px solid #667eea;
            }
        """)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        clear_button = QPushButton("清空对话")
        clear_button.setFixedHeight(36)
        clear_button.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #666;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 0px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #ececec;
                border-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        clear_button.clicked.connect(self.clear_chat)

        self.send_button = QPushButton("发送")
        self.send_button.setFixedHeight(36)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5568d3;
            }
            QPushButton:pressed {
                background-color: #4a5ac0;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.send_button.clicked.connect(self.send_message)

        button_layout.addWidget(clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)

        input_layout.addWidget(self.input_text)
        input_layout.addLayout(button_layout)

        container_layout.addWidget(input_container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(main_container)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 0)
        main_container.setGraphicsEffect(shadow)

        self.chat_scroll = chat_scroll

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.pos().y() < 50:
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.pos()
                event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False
        event.accept()

    def show_settings(self):
        settings_dialog = APIConfigDialog(None)  # 不设置父窗口
        # 连接配置保存信号
        settings_dialog.config_saved.connect(self.on_config_saved)
        if settings_dialog.exec() == QDialog.DialogCode.Accepted:
            self.api_config = settings_dialog.config

    def on_config_saved(self, message):
        """配置保存成功回调"""
        # 这个方法可以被外部重写或连接到状态栏
        pass

    def add_user_message(self, message):
        bubble = MessageBubble(message, is_user=True)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        self.messages.append({"role": "user", "content": message})
        self.scroll_to_bottom()

    def add_ai_message(self, message):
        bubble = MessageBubble(message, is_user=False)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        self.messages.append({"role": "assistant", "content": message})
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        QTimer.singleShot(
            100,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )

    def send_message(self):
        message = self.input_text.toPlainText().strip()
        if not message:
            return

        if not self.api_config.get("api_key"):
            QMessageBox.warning(self, "警告", "请先配置 API Key\n点击标题栏的齿轮图标进行配置")
            return

        self.add_user_message(message)
        self.input_text.clear()

        self.send_button.setEnabled(False)
        self.send_button.setText("发送中...")
        self.status_label.setText("● 思考中...")

        self.call_ai_api()

    def call_ai_api(self):
        self.api_thread = AIAPIThread(self.api_config, self.messages)
        self.api_thread.response_ready.connect(self.on_api_response)
        self.api_thread.error_occurred.connect(self.on_api_error)
        self.api_thread.start()

    def on_api_response(self, response):
        self.add_ai_message(response)
        self.send_button.setEnabled(True)
        self.send_button.setText("发送")
        self.status_label.setText("● 在线")

    def on_api_error(self, error_message):
        self.add_ai_message(f"抱歉，发生错误：{error_message}")
        self.send_button.setEnabled(True)
        self.send_button.setText("发送")
        self.status_label.setText("● 错误")

        QMessageBox.warning(self, "API 错误", error_message)

    def clear_chat(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.messages.clear()
        self.add_ai_message("对话已清空。有什么可以帮助您的吗？")


class FloatingButton(QWidget):
    """悬浮可移动按钮（只有这个窗口置顶）"""

    def __init__(self):
        super().__init__()
        self.ai_dialog = None
        self.init_ui()

    def init_ui(self):
        # 只有悬浮按钮使用置顶标志
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.main_button = DraggableButton("AI")
        self.main_button.setFixedSize(60, 60)
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

        self.main_button.mouseDoubleClickEvent = self.on_double_click

        self.close_btn = CloseButton()
        self.close_btn.clicked.connect(self.close_application)  # 调用close_application来关闭聊天框和悬浮按钮

        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        top_layout.addStretch()
        top_layout.addWidget(self.close_btn)
        top_layout.setContentsMargins(0, 0, 5, 0)

        layout.addLayout(top_layout)
        layout.addWidget(self.main_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(5, 0, 5, 5)
        layout.setSpacing(0)

        self.setLayout(layout)
        self.resize(70, 90)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 100, screen.height() - 150)

    def on_double_click(self, event):
        self.show_ai_dialog()
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 30px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #667eea;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #e0e0e0;
                margin: 5px 0px;
            }
        """)

        open_action = menu.addAction("打开 AI 助手")
        settings_action = menu.addAction("API 设置")
        menu.addSeparator()
        about_action = menu.addAction("关于")
        menu.addSeparator()
        exit_action = menu.addAction("退出")

        action = menu.exec(event.globalPos())

        if action == open_action:
            self.show_ai_dialog()
        elif action == settings_action:
            self.show_settings()
        elif action == exit_action:
            self.close_application()  # 调用close_application来关闭聊天框和悬浮按钮
        elif action == about_action:
            self.show_about()

    def show_settings(self):
        # 创建独立的配置对话框，不设置父窗口
        settings_dialog = APIConfigDialog(None)
        settings_dialog.exec()

    def show_about(self):
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle("关于")
        about_dialog.setFixedSize(300, 200)

        layout = QVBoxLayout()

        title = QLabel("AI 智能助手")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #667eea;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version = QLabel("版本 1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description = QLabel(
            '一个悬浮可移动的 AI 助手按钮\n\n支持自定义 API 配置\n双击或右键选择"打开"来启动对话'
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)

        ok_button = QPushButton("确定")
        ok_button.clicked.connect(about_dialog.accept)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #5568d3;
            }
        """)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignCenter)

        about_dialog.setLayout(layout)
        about_dialog.exec()

    def show_ai_dialog(self):
        # 创建独立的聊天对话框，不设置父窗口
        if self.ai_dialog is None or not self.ai_dialog.isVisible():
            self.ai_dialog = ChatAIDialog(None)  # 不设置父窗口
            self.ai_dialog.show()
        else:
            self.ai_dialog.activateWindow()
            self.ai_dialog.raise_()

    def close_application(self):
        # 关闭AI聊天对话框
        if self.ai_dialog and self.ai_dialog.isVisible():
            self.ai_dialog.close()
        # 只关闭悬浮按钮，不退出整个应用
        self.close()


def main():
    app = QApplication(sys.argv)

    simple_button = FloatingButton()
    simple_button.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
