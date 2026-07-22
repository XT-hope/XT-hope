"""
XML文本编辑器模块
提供XML语法高亮功能，用于编辑xvp、vsysvar等XML格式文件
仿照VSCode的XML高亮风格
"""
from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QFrame, QStyle, QApplication,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QSyntaxHighlighter, QTextDocument, QTextCursor, QKeySequence, QKeyEvent, QAction
from typing import List, Optional
import re


class XMLSyntaxHighlighter(QSyntaxHighlighter):
    """XML语法高亮器 - 深色版本，颜色更明显"""

    def __init__(self, document: QTextDocument, parent=None):
        super().__init__(document)

        # 定义语法规则和对应的格式
        self.highlighting_rules = []

        # XML标签格式 (如 <Panel>, </Panel>, <Object>) - 深蓝色
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("#0066CC"))  # 深蓝色
        tag_format.setFontWeight(QFont.Weight.Bold)

        # 匹配标签名: <Tag 或 </Tag
        tag_pattern = r"</?[a-zA-Z][a-zA-Z0-9._]*"
        self.highlighting_rules.append((re.compile(tag_pattern), tag_format))

        # 标签结束符号 (> 和 />) - 深蓝色
        tag_end_format = QTextCharFormat()
        tag_end_format.setForeground(QColor("#0066CC"))
        self.highlighting_rules.append((re.compile(r"/>|>"), tag_end_format))

        # 属性名格式 (如 Type="...", Name="...") - 深青色
        attr_name_format = QTextCharFormat()
        attr_name_format.setForeground(QColor("#008B8B"))  # 深青色
        attr_pattern = r'\b([a-zA-Z][a-zA-Z0-9._]*)\s*='
        self.highlighting_rules.append((re.compile(attr_pattern), attr_name_format))

        # 属性值格式 (双引号内的字符串) - 深红棕色
        attr_value_format = QTextCharFormat()
        attr_value_format.setForeground(QColor("#A52A2A"))  # 深红棕色
        attr_value_pattern = r'"[^"]*"'
        self.highlighting_rules.append((re.compile(attr_value_pattern), attr_value_format))

        # XML注释格式 <!-- comment --> - 深绿色
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#228B22"))  # 深绿色
        comment_pattern = r'<!--.*?-->'
        self.highlighting_rules.append((re.compile(comment_pattern), comment_format))

        # XML声明格式 <?xml ...?> - 深紫色
        declaration_format = QTextCharFormat()
        declaration_format.setForeground(QColor("#8B008B"))  # 深紫色
        declaration_pattern = r'<\?xml[^>]*\?>'
        self.highlighting_rules.append((re.compile(declaration_pattern), declaration_format))

        # 等号格式 - 黑色
        equal_format = QTextCharFormat()
        equal_format.setForeground(QColor("#333333"))  # 深灰色
        self.highlighting_rules.append((re.compile(r'='), equal_format))

        # 特殊字符 &xxx; 格式 - 深黄色
        entity_format = QTextCharFormat()
        entity_format.setForeground(QColor("#B8860B"))  # 深黄色
        entity_pattern = r'&[a-zA-Z]+;'
        self.highlighting_rules.append((re.compile(entity_pattern), entity_format))

    def highlightBlock(self, text: str) -> None:
        """高亮文本块"""
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class XMLTextEditor(QPlainTextEdit):
    """XML文本编辑器，支持语法高亮和查找功能"""

    content_changed = pyqtSignal()
    save_to_file_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 设置字体
        font = QFont("Consolas", 10)
        font.setFixedPitch(True)
        self.setFont(font)

        # 设置语法高亮
        self.highlighter = XMLSyntaxHighlighter(self.document())

        # 查找栏
        self.find_bar = None
        self._original_content = ""
        self._file_path = ""
        self._file_name = ""

        # 添加快捷键
        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        """设置快捷键"""
        # Ctrl+S 保存
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        self.addAction(save_action)

        # Ctrl+F 查找
        find_action = QAction("查找", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.show_find_bar)
        self.addAction(find_action)

        # Escape 关闭查找栏
        escape_action = QAction("关闭查找", self)
        escape_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        escape_action.triggered.connect(self.hide_find_bar)
        self.addAction(escape_action)

    def _on_save(self) -> None:
        """保存文件"""
        if self._file_path:
            try:
                content = self.toPlainText()
                with open(self._file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self._original_content = content
                self.document().setModified(False)
                self.save_to_file_requested.emit()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存文件失败: {e}")

    def set_file_info(self, file_path: str, file_name: str) -> None:
        """设置文件信息"""
        self._file_path = file_path
        self._file_name = file_name

    def get_file_path(self) -> str:
        """获取文件路径"""
        return self._file_path

    def get_file_name(self) -> str:
        """获取文件名"""
        return self._file_name

    def set_content(self, content: str) -> None:
        """设置编辑器内容"""
        self._original_content = content
        self.setPlainText(content)
        self.document().setModified(False)

    def get_content(self) -> str:
        """获取编辑器内容"""
        return self.toPlainText()

    def is_modified(self) -> bool:
        """检查内容是否修改"""
        return self.document().isModified()

    def show_find_bar(self) -> None:
        """显示查找栏"""
        if self.find_bar is None:
            self.find_bar = XMLFindBar(self)
            self.find_bar.find_next_requested.connect(self.find_next)
            self.find_bar.find_previous_requested.connect(self.find_previous)
            self.find_bar.close_requested.connect(self.hide_find_bar)

        parent_widget = self.parent()
        if parent_widget and isinstance(parent_widget, QWidget):
            layout = parent_widget.layout()
            if layout:
                layout.addWidget(self.find_bar)

        self.find_bar.show()
        self.find_bar.focus_find_input()

    def hide_find_bar(self) -> None:
        """隐藏查找栏"""
        if self.find_bar:
            self.find_bar.hide()

    def find_next(self, text: str, case_sensitive: bool = False) -> None:
        """查找下一个"""
        if not text:
            return

        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively

        cursor = self.textCursor()
        cursor.setPosition(cursor.selectionEnd())

        found_cursor = self.document().find(text, cursor, flags)
        if not found_cursor.isNull():
            self.setTextCursor(found_cursor)
        else:
            # 从文档开头重新查找
            found_cursor = self.document().find(text, QTextCursor(), flags)
            if not found_cursor.isNull():
                self.setTextCursor(found_cursor)

    def find_previous(self, text: str, case_sensitive: bool = False) -> None:
        """查找上一个"""
        if not text:
            return

        flags = QTextDocument.FindFlag.FindBackward
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively

        cursor = self.textCursor()
        cursor.setPosition(cursor.selectionStart())

        found_cursor = self.document().find(text, cursor, flags)
        if not found_cursor.isNull():
            self.setTextCursor(found_cursor)
        else:
            # 从文档末尾重新查找
            cursor = QTextCursor(self.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            found_cursor = self.document().find(text, cursor, flags)
            if not found_cursor.isNull():
                self.setTextCursor(found_cursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """按键事件处理"""
        super().keyPressEvent(event)
        if event.text():
            self.content_changed.emit()


class XMLFindBar(QFrame):
    """XML编辑器的查找栏"""

    find_next_requested = pyqtSignal(str, bool)
    find_previous_requested = pyqtSignal(str, bool)
    close_requested = pyqtSignal()

    def __init__(self, editor: XMLTextEditor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #f0f0f0; padding: 4px;")

        self.init_ui()

    def init_ui(self) -> None:
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 查找标签
        find_label = QLabel("查找:")
        layout.addWidget(find_label)

        # 查找输入框
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("输入查找内容...")
        self.find_input.setMinimumWidth(200)
        self.find_input.returnPressed.connect(self.on_find_next)
        layout.addWidget(self.find_input)

        # 大小写敏感复选框
        self.case_sensitive_checkbox = QCheckBox("区分大小写")
        layout.addWidget(self.case_sensitive_checkbox)

        # 查找下一个按钮
        find_next_btn = QPushButton("下一个")
        find_next_btn.clicked.connect(self.on_find_next)
        layout.addWidget(find_next_btn)

        # 查找上一个按钮
        find_previous_btn = QPushButton("上一个")
        find_previous_btn.clicked.connect(self.on_find_previous)
        layout.addWidget(find_previous_btn)

        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(close_btn)

    def on_find_next(self) -> None:
        """查找下一个"""
        text = self.find_input.text()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        self.find_next_requested.emit(text, case_sensitive)

    def on_find_previous(self) -> None:
        """查找上一个"""
        text = self.find_input.text()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        self.find_previous_requested.emit(text, case_sensitive)

    def focus_find_input(self) -> None:
        """聚焦查找输入框"""
        self.find_input.setFocus()
        self.find_input.selectAll()

    def showEvent(self, event) -> None:
        """显示事件"""
        super().showEvent(event)
        self.focus_find_input()
