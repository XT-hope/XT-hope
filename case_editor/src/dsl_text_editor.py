"""
DSL文本编辑器模块
提供简单的文本编辑功能，用于直接编辑DSL文件
"""
from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QFrame, QStyle, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QSyntaxHighlighter, QTextDocument, QTextCursor, QKeySequence, QKeyEvent, QAction
from typing import List, Optional
import re


class DSLSyntaxHighlighter(QSyntaxHighlighter):
    """DSL语法高亮器"""
    
    def __init__(self, document: QTextDocument, parent=None):
        super().__init__(document)
        
        # 定义语法规则和对应的格式
        self.highlighting_rules = []
        
        # 关键字格式
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))  # VS Code蓝色
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "CASE", "META", "SET", "CHECK", "set", "check",
            "wait", "then", "async", "keep_dynamic", "timeout", "duration", "count", "comment"
        ]
        for keyword in keywords:
            pattern = f"\\b{keyword}\\b"
            self.highlighting_rules.append((re.compile(pattern), keyword_format))
        
        # 信号类型格式
        signal_type_format = QTextCharFormat()
        signal_type_format.setForeground(QColor("#4EC9B0"))  # 青色
        signal_type_format.setFontWeight(QFont.Weight.Bold)
        signal_types = ["sig::", "env::", "sys::"]
        for sig_type in signal_types:
            pattern = f"{sig_type}"
            self.highlighting_rules.append((re.compile(pattern), signal_type_format))

        # 步骤标签格式 (S1, C1等)
        label_format = QTextCharFormat()
        label_format.setForeground(QColor("#DCDCAA"))  # 黄色
        label_format.setFontWeight(QFont.Weight.Bold)
        label_pattern = r"\b[SC]\d+\b:"
        self.highlighting_rules.append((re.compile(label_pattern), label_format))

        # 数字格式
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # 浅绿色
        number_pattern = r"\b0x[0-9A-Fa-f]+\b|\b\d+\b"
        self.highlighting_rules.append((re.compile(number_pattern), number_format))

        # CAN通道格式（放在数字格式之后，覆盖数字颜色）
        channel_format = QTextCharFormat()
        channel_format.setForeground(QColor("#CE9178"))  # 橙色
        channel_pattern = r"CAN\s+\d+"
        self.highlighting_rules.append((re.compile(channel_pattern), channel_format))
        
        # 时间单位格式
        time_format = QTextCharFormat()
        time_format.setForeground(QColor("#C586C0"))  # 紫色
        time_pattern = r"\b\d+\s*(ms|s)\b"
        self.highlighting_rules.append((re.compile(time_pattern), time_format))
        
        # 布尔值格式
        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor("#569CD6"))  # 蓝色
        bool_pattern = r"\b(True|False|TRUE|FALSE)\b"
        self.highlighting_rules.append((re.compile(bool_pattern), bool_format))
        
                
        # 比较运算符格式
        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor("#000000"))  # 黑色
        operators = ["!=", ">", "<"]
        for op in operators:
            pattern = f"{re.escape(op)}"
            self.highlighting_rules.append((re.compile(pattern), operator_format))
        
        # 逻辑运算符格式
        logic_format = QTextCharFormat()
        logic_format.setForeground(QColor("#569CD6"))  # 蓝色
        logic_operators = ["&&", "\\|\\|", "!"]
        for op in logic_operators:
            pattern = f"{op}"
            self.highlighting_rules.append((re.compile(pattern), logic_format))
    
    def highlightBlock(self, text: str) -> None:
        """高亮文本块"""
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class FindBar(QFrame):
    """查找栏"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_match = 0
        self._total_matches = 0
        self._build_ui()
        self.hide()
    
    def _build_ui(self) -> None:
        """构建UI"""
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QLineEdit {
                padding: 4px 8px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: white;
                min-height: 24px;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: #ffffff;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #e6e6e6;
            }
            QPushButton:pressed {
                background-color: #d4d4d4;
            }
            QCheckBox {
                spacing: 5px;
            }
            QLabel {
                color: #666666;
                font-size: 12px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        
        # 查找输入框
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("查找")
        self.find_edit.setMinimumWidth(200)
        self.find_edit.textChanged.connect(self._on_text_changed)
        self.find_edit.returnPressed.connect(self._on_find_next)
        layout.addWidget(self.find_edit)
        
        # 查找上一个按钮 - 使用向上箭头图标
        self.find_prev_btn = QPushButton()
        self.find_prev_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.find_prev_btn.setFixedSize(28, 28)
        self.find_prev_btn.setToolTip("查找上一个 (Shift+Enter)")
        self.find_prev_btn.clicked.connect(self._on_find_prev)
        layout.addWidget(self.find_prev_btn)
        
        # 查找下一个按钮 - 使用向下箭头图标
        self.find_next_btn = QPushButton()
        self.find_next_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.find_next_btn.setFixedSize(28, 28)
        self.find_next_btn.setToolTip("查找下一个 (Enter)")
        self.find_next_btn.clicked.connect(self._on_find_next)
        layout.addWidget(self.find_next_btn)
        
        # 结果计数标签
        self.result_label = QLabel("0 of 0")
        self.result_label.setMinimumWidth(80)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.result_label)
        
        # 选项 - 使用文本按钮
        self.case_sensitive_btn = QPushButton("Aa")
        self.case_sensitive_btn.setFixedSize(32, 28)
        self.case_sensitive_btn.setToolTip("区分大小写")
        self.case_sensitive_btn.setCheckable(True)
        self.case_sensitive_btn.clicked.connect(self._on_find_next)
        layout.addWidget(self.case_sensitive_btn)
        
        self.whole_words_btn = QPushButton("|ab|")
        self.whole_words_btn.setFixedSize(32, 28)
        self.whole_words_btn.setToolTip("全字匹配")
        self.whole_words_btn.setCheckable(True)
        self.whole_words_btn.clicked.connect(self._on_find_next)
        layout.addWidget(self.whole_words_btn)
        
        layout.addStretch()
        
        # 关闭按钮 - 使用关闭图标
        self.close_btn = QPushButton()
        self.close_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)
    
    def update_result_label(self, current: int, total: int) -> None:
        """更新结果标签"""
        self._current_match = current
        self._total_matches = total
        
        if total == 0:
            self.result_label.setText("No results")
            self.result_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        else:
            self.result_label.setText(f"{current} of {total}")
            self.result_label.setStyleSheet("color: #666666; font-size: 12px;")
    
    def _on_text_changed(self, text: str) -> None:
        """文本改变时自动查找"""
        if text:
            self._on_find_next()
    
    def _on_find_next(self) -> None:
        """查找下一个"""
        text = self.find_edit.text()
        if text:
            self.find_next.emit(text, self.case_sensitive_btn.isChecked(),
                              self.whole_words_btn.isChecked(), True)
    
    def _on_find_prev(self) -> None:
        """查找上一个"""
        text = self.find_edit.text()
        if text:
            self.find_next.emit(text, self.case_sensitive_btn.isChecked(),
                              self.whole_words_btn.isChecked(), False)
    
    def showEvent(self, event) -> None:
        """显示事件"""
        super().showEvent(event)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
    
    def keyPressEvent(self, event) -> None:
        """按键事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
    
    # 信号
    find_next = pyqtSignal(str, bool, bool, bool)  # text, case_sensitive, whole_words, forward


class DSLTextEditor(QPlainTextEdit):
    """DSL文本编辑器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置编辑器属性
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 12))
        
        # 设置语法高亮
        self.highlighter = DSLSyntaxHighlighter(self.document())
        
        # 创建查找栏
        self.find_bar = FindBar(self)
        self.find_bar.find_next.connect(self._on_find_requested)
        self.find_bar.hide()
        
        # 安装事件过滤器来处理快捷键
        self.installEventFilter(self)
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """按键事件处理，阻止只读模式下的粘贴操作"""
        # 检查是否是 Ctrl+V 粘贴操作且编辑器为只读模式
        if (event.key() == Qt.Key.Key_V and
            event.modifiers() == Qt.KeyboardModifier.ControlModifier and
            self.isReadOnly()):
            # 阻止粘贴操作
            return
        # 其他按键正常处理
        super().keyPressEvent(event)
    
    def get_content(self) -> str:
        """获取编辑器内容"""
        return self.toPlainText()
    
    def set_content(self, content: str) -> None:
        """设置编辑器内容"""
        self.setPlainText(content)
    
    def validate(self) -> List[str]:
        """验证DSL格式"""
        errors = []
        content = self.toPlainText()
        
        # 检查CASE行
        if not re.search(r'^CASE:', content, re.MULTILINE):
            errors.append("缺少CASE行")
        
        # 检查META行
        if not re.search(r'^META:', content, re.MULTILINE):
            errors.append("缺少META行")
        else:
            # 检查META中的场景ID和场景名称
            meta_match = re.search(r'^META:\s*(.*)$', content, re.MULTILINE)
            if meta_match:
                meta_content = meta_match.group(1)
                # 检查场景ID
                if not re.search(r'\bscenario_id=\S+', meta_content):
                    errors.append("META中缺少场景ID（scenario_id）")
                # 检查场景名称
                if not re.search(r'\bscenario_name=\S+', meta_content):
                    errors.append("META中缺少场景名称（scenario_name）")
                # 检查测试点
                if not re.search(r'\btest_point=\S+', meta_content):
                    errors.append("META中缺少测试点（test_point）")
        
        # 检查[SET]部分
        if not re.search(r'\[SET\]', content):
            errors.append("缺少[SET]部分")
        
        # 检查[CHECK]部分
        if not re.search(r'\[CHECK\]', content):
            errors.append("缺少[CHECK]部分")
        
        return errors
    
    # 编辑操作 - 调用父类 QPlainTextEdit 的方法
    def undo(self) -> None:
        """撤销"""
        super().undo()
    
    def redo(self) -> None:
        """重做"""
        super().redo()
    
    def cut(self) -> None:
        """剪切"""
        super().cut()
    
    def copy(self) -> None:
        """复制"""
        super().copy()
    
    def paste(self) -> None:
        """粘贴"""
        # 如果是只读模式，不允许粘贴
        if self.isReadOnly():
            return
        super().paste()
    
    def selectAll(self) -> None:
        """全选"""
        super().selectAll()
    
    def eventFilter(self, obj, event) -> bool:
        """事件过滤器"""
        if obj == self and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_F and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Ctrl+F - 显示查找栏
                self.find_bar.show()
                return True
        return super().eventFilter(obj, event)
    
    def _on_find_requested(self, text: str, case_sensitive: bool, whole_words: bool, forward: bool) -> None:
        """处理查找请求"""
        if not text:
            self.find_bar.update_result_label(0, 0)
            return
        
        # 构建查找选项
        find_options = QTextDocument.FindFlag(0)
        if case_sensitive:
            find_options |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_words:
            find_options |= QTextDocument.FindFlag.FindWholeWords
        if not forward:
            find_options |= QTextDocument.FindFlag.FindBackward
        
        # 计算所有匹配项
        total_matches = self._count_matches(text, case_sensitive, whole_words)
        
        # 执行查找
        found = self.find(text, find_options)
        
        if not found:
            # 如果没找到，从文档开头/结尾重新搜索
            cursor = self.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            found = self.find(text, find_options)
        
        # 更新结果标签
        if found:
            current_match = self._get_current_match_index(text, case_sensitive, whole_words)
            # 如果获取的索引为0但有匹配项，说明光标不在匹配项中，设置为1
            if current_match == 0 and total_matches > 0:
                current_match = 1
            self.find_bar.update_result_label(current_match, total_matches)
        else:
            self.find_bar.update_result_label(0, total_matches)
    
    def _count_matches(self, text: str, case_sensitive: bool, whole_words: bool) -> int:
        """计算匹配项总数"""
        # 使用正则表达式查找所有匹配项
        flags = 0
        if not case_sensitive:
            flags = re.IGNORECASE
        
        if whole_words:
            pattern = r'\b' + re.escape(text) + r'\b'
        else:
            pattern = re.escape(text)
        
        content = self.toPlainText()
        matches = list(re.finditer(pattern, content, flags))
        return len(matches)
    
    def _get_current_match_index(self, text: str, case_sensitive: bool, whole_words: bool) -> int:
        """获取当前匹配项的索引"""
        # 使用正则表达式查找所有匹配项
        flags = 0
        if not case_sensitive:
            flags = re.IGNORECASE
        
        if whole_words:
            pattern = r'\b' + re.escape(text) + r'\b'
        else:
            pattern = re.escape(text)
        
        content = self.toPlainText()
        matches = list(re.finditer(pattern, content, flags))
        
        # 获取当前光标位置
        current_pos = self.textCursor().position()
        
        # 找到当前光标位置对应的匹配项
        for i, match in enumerate(matches, 1):
            if match.start() <= current_pos <= match.end():
                return i
        
        # 如果光标不在任何匹配项中，返回 0
        return 0
    
    def resizeEvent(self, event) -> None:
        """调整大小事件"""
        super().resizeEvent(event)
        # 将查找栏定位到顶部中央
        if self.find_bar:
            # 计算查找栏的宽度
            bar_width = self.find_bar.sizeHint().width()
            # 限制最大宽度，避免超出编辑器
            max_width = min(bar_width, self.width() - 40)
            self.find_bar.setFixedWidth(max_width)
            # 居中显示
            x = (self.width() - max_width) // 2
            self.find_bar.move(x, 10)
