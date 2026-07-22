from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QToolBar, QStatusBar, QTreeWidget, QTreeWidgetItem,
    QFileDialog, QMessageBox, QTabWidget, QLabel, QPushButton,
    QDockWidget, QTextEdit, QComboBox, QSpinBox, QCheckBox,
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QInputDialog,
    QAbstractItemView, QMenu, QProgressDialog,QApplication
)
from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher, QItemSelectionModel, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont, QShortcut
from pathlib import Path, PurePosixPath
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
import json
import sys
import os
import re
import shutil
import subprocess
import platform
import time

from .config_manager import ConfigManager
from .project_manager import ProjectManager
from .dbc_parser import DBCParser
from .case_editor import ModularCaseEditor
from .dsl_text_editor import DSLTextEditor
from .xml_text_editor import XMLTextEditor
from .dialogs import (
    NewProjectDialog, DBCMappingDialog, SystemVariableDialog,
    AIQuestionDialog, OSSConfigDialog, DBCConverterDialog, AIConfigDialog,
    ReadOnlyTextEdit, CANoeProjectDialog, SimulinkFileDialog, SceneMappingDialog,
    CANoePanelDialog, PanelFileInfoDialog, CANoeCAPLDialog
)
from .ai_tool import ChatAIDialog, FloatingButton, APIConfigDialog
from .run_case import Main


class ProjectTreeWidget(QTreeWidget):
    """自定义项目树控件，支持键盘快捷键"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None
        self.copy_shortcut = None
        self.paste_shortcut = None
        self._last_click_modifiers = Qt.KeyboardModifier(0)
        self._mouse_pressed = False
    
        self.setUniformRowHeights(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAutoScroll(False)
        self.setAnimated(False)
    
        self._last_wheel_time = 0.0
        self._wheel_angle_accumulated = 0
    
        self._smooth_scroll_target = 0.0
        self._smooth_scroll_velocity = 0.0
        self._smooth_scroll_timer = QTimer(self)
        self._smooth_scroll_timer.setInterval(8)
        self._smooth_scroll_timer.timeout.connect(self._on_smooth_scroll_tick)
    
        self.verticalScrollBar().setSingleStep(max(self.fontMetrics().height(), 20))
        
    def _enqueue_smooth_scroll(self, delta_pixels: float) -> None:
        """把滚轮位移加入平滑滚动队列"""
        if not delta_pixels:
            return

        bar = self.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            return

        if not self._smooth_scroll_timer.isActive():
            self._smooth_scroll_target = float(bar.value())
            self._smooth_scroll_velocity = 0.0

        self._smooth_scroll_target += float(delta_pixels)
        self._smooth_scroll_target = max(
            float(bar.minimum()),
            min(float(bar.maximum()), self._smooth_scroll_target)
        )

        # 提供“惯性推进”手感
        self._smooth_scroll_velocity += float(delta_pixels) * 0.24

        if not self._smooth_scroll_timer.isActive():
            self._smooth_scroll_timer.start()
            
    def _on_smooth_scroll_tick(self) -> None:
        """定时推进平滑滚动动画"""
        bar = self.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            self._smooth_scroll_timer.stop()
            self._smooth_scroll_velocity = 0.0
            return

        current = float(bar.value())
        target = self._smooth_scroll_target
        distance = target - current

        # 阻尼 + 追踪，接近编辑器文件树的滚动手感
        self._smooth_scroll_velocity = self._smooth_scroll_velocity * 0.72 + distance * 0.28
        next_value = current + self._smooth_scroll_velocity

        min_v = float(bar.minimum())
        max_v = float(bar.maximum())
        if next_value < min_v:
            next_value = min_v
            self._smooth_scroll_velocity = 0.0
        elif next_value > max_v:
            next_value = max_v
            self._smooth_scroll_velocity = 0.0

        bar.setValue(int(round(next_value)))

        if abs(target - next_value) < 0.6 and abs(self._smooth_scroll_velocity) < 0.45:
            bar.setValue(int(round(target)))
            self._smooth_scroll_velocity = 0.0
            self._smooth_scroll_timer.stop()
            
    def is_smooth_scrolling(self) -> bool:
        """当前是否处于平滑滚动中"""
        return self._smooth_scroll_timer.isActive()

    def mousePressEvent(self, event):
        """捕获鼠标按下时的修饰键状态（比 Release 更可靠，意图明确）"""
        self._last_click_modifiers = event.modifiers()
        self._mouse_pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._mouse_pressed = False

    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.copy_shortcut.activated.connect(self.on_copy_shortcut)

        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.paste_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.paste_shortcut.activated.connect(self.on_paste_shortcut)
        
    def wheelEvent(self, event):
        """稳定滚动：无惯性动画，角度累积 + 像素余量，降低抖动"""
        self._last_wheel_time = time.monotonic()
        scrollbar = self.verticalScrollBar()
    
        # 如果历史版本启用了平滑动画，先停掉，避免双重滚动逻辑叠加导致抖动
        smooth_timer = getattr(self, "_smooth_scroll_timer", None)
        if smooth_timer is not None and smooth_timer.isActive():
            smooth_timer.stop()
            if hasattr(self, "_smooth_scroll_velocity"):
                self._smooth_scroll_velocity = 0.0
            if hasattr(self, "_smooth_scroll_target"):
                self._smooth_scroll_target = float(scrollbar.value())
    
        lines_per_step = float(getattr(self, "_wheel_lines_per_step", 2.0))
        min_line_px = int(getattr(self, "_wheel_min_line_px", 20))
    
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull() and pixel_delta.y() != 0:
            # 保留小数余量，避免高精度输入被截断后产生细微抖动
            remainder = getattr(self, "_wheel_pixel_remainder", 0.0) - float(pixel_delta.y())
            move = int(remainder)
            self._wheel_pixel_remainder = remainder - move
            if move != 0:
                scrollbar.setValue(scrollbar.value() + move)
            event.accept()
            return
    
        angle = event.angleDelta().y()
        if angle == 0:
            event.ignore()
            return
    
        accumulated = getattr(self, "_wheel_angle_accumulated", 0) + angle
        steps = int(accumulated / 120)  # 向 0 截断，正负方向一致
        self._wheel_angle_accumulated = accumulated - steps * 120
    
        if steps == 0:
            event.accept()
            return
    
        line_h = max(scrollbar.singleStep(), self.fontMetrics().height(), min_line_px)
        delta_pixels = int(round(steps * line_h * lines_per_step))
        scrollbar.setValue(scrollbar.value() - delta_pixels)
        event.accept()
        
    def on_copy_shortcut(self):
        """Ctrl+C 快捷键处理 - 支持 DSL、Automation 和 Test Results 多选复制"""
        if not self.main_window:
            return
        selected_items = self.selectedItems()
        if not selected_items:
            return

        automation_items = []
        test_results_items = []
        all_automation = True
        all_test_results = True

        for si in selected_items:
            d = si.data(0, Qt.ItemDataRole.UserRole)
            if d and d.get("type") in ("automation_file", "automation_directory"):
                automation_items.append(d)
                all_test_results = False
            elif d and d.get("type") in ("test_results_file", "test_results_directory"):
                test_results_items.append(d)
                all_automation = False
            else:
                all_automation = False
                all_test_results = False

        if all_automation and automation_items:
            if len(automation_items) == 1:
                d = automation_items[0]
                if d.get("type") == "automation_file":
                    self.main_window.copy_automation_file(d.get("path", ""), d.get("case_type", "py"))
                else:
                    self.main_window.copy_automation_directory(d.get("path", ""), d.get("case_type", "py"))
            else:
                self.main_window.copy_automation_items(automation_items)
            return

        if all_test_results and test_results_items:
            if len(test_results_items) == 1:
                d = test_results_items[0]
                if d.get("type") == "test_results_file":
                    self.main_window.copy_test_results_file(d.get("path", ""), d.get("data_type", "trace"))
                else:
                    self.main_window.copy_test_results_directory(d.get("path", ""), d.get("data_type", "trace"))
            else:
                self.main_window.copy_test_results_items(test_results_items)
            return

        items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in selected_items]
        self.main_window.copy_dsl_items(items_data)

    def on_paste_shortcut(self):
        """Ctrl+V 快捷键处理 - 支持 automation_items 和 test_results_items 多项粘贴"""
        if not self.main_window or not self.main_window.clipboard:
            return
        current_item = self.currentItem()
        if not current_item:
            return

        item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        clipboard_type = self.main_window.clipboard.get("type")
        is_automation_clipboard = clipboard_type in ("automation_file", "automation_directory", "automation_items")
        is_test_results_clipboard = clipboard_type in ("test_results_file", "test_results_directory", "test_results_items")

        if is_automation_clipboard:
            case_type = self.main_window.clipboard.get("case_type", "py")
            if clipboard_type == "automation_items":
                items = self.main_window.clipboard.get("items", [])
                if items:
                    case_type = items[0].get("case_type", "py")
            target_directory = self._resolve_automation_paste_target(current_item, item_data, case_type)
            if target_directory is not None:
                self.main_window.paste_automation_item(target_directory, case_type)
        elif is_test_results_clipboard:
            data_type = self.main_window.clipboard.get("data_type", "trace")
            if clipboard_type == "test_results_items":
                items = self.main_window.clipboard.get("items", [])
                if items:
                    data_type = items[0].get("data_type", "trace")
            target_directory = self._resolve_test_results_paste_target(current_item, item_data, data_type)
            if target_directory is not None:
                self.main_window.paste_test_results_item(target_directory, data_type)
        else:
            target_directory = self._resolve_dsl_paste_target(current_item, item_data)
            if target_directory is not None:
                self.main_window.paste_dsl_item(target_directory)

    def _resolve_automation_paste_target(self, current_item, item_data, case_type) -> Optional[str]:
        """解析 Automation Cases 粘贴目标目录，返回 None 表示无效目标"""
        if item_data and item_data.get("type") == "automation_directory":
            return item_data.get("path", "")
        if item_data and item_data.get("type") == "automation_file":
            file_path = item_data.get("path", "")
            parent_dir = str(PurePosixPath(file_path).parent)
            return parent_dir if parent_dir != "." else ""

        item_text = current_item.text(0)
        if item_text in ("py_cases", "json_cases"):
            return ""

        tree_parent = current_item.parent()
        if tree_parent and tree_parent.text(0) in ("py_cases", "json_cases"):
            return ""
        return None

    def _resolve_dsl_paste_target(self, current_item, item_data) -> Optional[str]:
        """解析 DSL Cases 粘贴目标目录，返回 None 表示无效目标"""
        if item_data and item_data.get("type") == "directory":
            return item_data.get("path", "")
        if item_data and item_data.get("type") == "file":
            file_path = item_data.get("path", "")
            parent_dir = str(PurePosixPath(file_path).parent)
            return parent_dir if parent_dir != "." else ""

        tree_parent = current_item.parent()
        if (tree_parent and tree_parent.text(0) == "DSL Cases") or current_item.text(0) == "DSL Cases":
            return ""
        return None

    def _resolve_test_results_paste_target(self, current_item, item_data, data_type) -> Optional[str]:
        """解析 Test Results 粘贴目标目录，返回 None 表示无效目标"""
        if item_data and item_data.get("type") == "test_results_directory":
            return item_data.get("path", "")
        if item_data and item_data.get("type") == "test_results_file":
            file_path = item_data.get("path", "")
            parent_dir = str(PurePosixPath(file_path).parent)
            return parent_dir if parent_dir != "." else ""

        item_text = current_item.text(0)
        if item_text in ("trace data", "record data", "log data", "report data"):
            return ""

        tree_parent = current_item.parent()
        if tree_parent and tree_parent.text(0) in ("trace data", "record data", "log data", "report data"):
            return ""
        return None


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.project_manager = ProjectManager()
        self.dbc_parser = DBCParser()

        self.current_case_name: Optional[str] = None
        self.current_case_directory: str = ""
        self.current_case_modified: bool = False

        # {file_key: [editor1, editor2, ...]}
        self.file_editors_map: Dict[str, List[Any]] = {}

        self.clipboard: Optional[Dict[str, Any]] = None

        self.ai_dialog = None
        self.floating_button = None

        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)
        self.file_watcher.fileChanged.connect(self.on_file_changed)
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_project_tree)

        # 文件系统事件节流状态（避免滚轮后立即触发全量树刷新）
        self._last_fs_event_time = 0.0
        self._pending_fs_change = False
        self._pending_dir_change = False
        self._last_tree_refresh_time = 0.0
        self._last_watcher_sync_time = 0.0
        self._min_tree_refresh_interval = 0.12

        self._undo_stack: List[Dict[str, Any]] = []
        self._max_undo_history = 50

        self.init_ui()
        self.init_menu()
        self.init_toolbar()
        self.init_statusbar()
        self.load_recent_projects()
        self.update_window_title()

    # ==================== UI 初始化 ====================

    def init_ui(self) -> None:
        """初始化用户界面"""
        self.setWindowTitle("HIL TEST")
        self.resize(1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧 - 项目浏览器
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        self.project_tree = ProjectTreeWidget()
        self.project_tree.setHeaderLabel("项目浏览器")
        self.project_tree.set_main_window(self)
        self.project_tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        self.project_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.project_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.project_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.project_tree.setExpandsOnDoubleClick(False)

        self._expand_click_timer = QTimer()
        self._expand_click_timer.setSingleShot(True)
        self._expand_click_timer.setInterval(QApplication.doubleClickInterval())
        self._expand_click_timer.timeout.connect(self._on_expand_click_timeout)
        self._pending_expand_item = None

        left_layout.addWidget(self.project_tree)

        splitter.addWidget(left_panel)

        # 右侧 - 编辑器
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.close_editor_tab)
        self.editor_tabs.currentChanged.connect(self.on_tab_changed)
        right_layout.addWidget(self.editor_tabs)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 1100])

        # AI 问答停靠窗口
        self.ai_dock = QDockWidget("AI 助手", self)
        self.ai_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.ai_text = ReadOnlyTextEdit()
        self.ai_dock.setWidget(self.ai_text)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ai_dock)
        self.ai_dock.hide()

    def init_menu(self) -> None:
        """初始化菜单栏"""
        menubar = self.menuBar()

        # === 文件菜单 ===
        file_menu = menubar.addMenu("文件(&F)")

        new_project_action = QAction("新建项目(&N)...", self)
        new_project_action.setShortcut(QKeySequence.StandardKey.New)
        new_project_action.setStatusTip("创建新项目")
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)

        open_project_action = QAction("打开项目(&O)...", self)
        open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        open_project_action.setStatusTip("打开现有项目")
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()

        save_project_action = QAction("保存项目(&S)", self)
        save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        save_project_action.setStatusTip("保存项目")
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)

        close_project_action = QAction("关闭项目(&C)", self)
        close_project_action.setStatusTip("关闭当前项目")
        close_project_action.triggered.connect(self.close_project)
        file_menu.addAction(close_project_action)

        file_menu.addSeparator()

        self.recent_menu = file_menu.addMenu("最近项目(&R)")
        self.update_recent_menu()

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.setStatusTip("退出应用程序")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # === 编辑菜单 ===
        edit_menu = menubar.addMenu("编辑(&E)")

        undo_action = QAction("撤销(&U)", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("重做(&R)", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("剪切(&T)", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        cut_action.triggered.connect(self.cut)
        edit_menu.addAction(cut_action)

        copy_action = QAction("复制(&C)", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy_action.triggered.connect(self.copy)
        edit_menu.addAction(copy_action)

        paste_action = QAction("粘贴(&P)", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        paste_action.triggered.connect(self.paste)
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        find_action = QAction("查找(&F)...", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.find)
        edit_menu.addAction(find_action)

        # === 选择菜单 ===
        selection_menu = menubar.addMenu("选择(&S)")

        select_all_action = QAction("全选(&A)", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self.select_all)
        selection_menu.addAction(select_all_action)

        # === 项目菜单 ===
        project_menu = menubar.addMenu("项目(&P)")

        canoe_menu = project_menu.addMenu("CANoe(&C)")

        add_dbc_action = QAction("添加DBC文件(&D)...", self)
        add_dbc_action.setStatusTip("添加DBC文件到项目")
        add_dbc_action.triggered.connect(self.add_dbc_file)
        canoe_menu.addAction(add_dbc_action)

        add_env_dbc_action = QAction("添加环境变量DBC文件(&E)...", self)
        add_env_dbc_action.setStatusTip("添加环境变量DBC文件到项目")
        add_env_dbc_action.triggered.connect(self.add_env_dbc_file)
        canoe_menu.addAction(add_env_dbc_action)

        add_sysvar_action = QAction("添加系统变量文件(&S)...", self)
        add_sysvar_action.setStatusTip("添加系统变量文件到项目")
        add_sysvar_action.triggered.connect(self.add_system_variable_file)
        canoe_menu.addAction(add_sysvar_action)

        canoe_menu.addSeparator()

        config_mapping_action = QAction("配置CAN通道映射(&M)...", self)
        config_mapping_action.setStatusTip("配置DBC文件到CAN通道的映射")
        config_mapping_action.triggered.connect(self.config_can_mapping)
        canoe_menu.addAction(config_mapping_action)

        canoe_menu.addSeparator()

        config_canoe_project_action = QAction("配置工程文件(&P)...", self)
        config_canoe_project_action.setStatusTip("配置CANoe工程文件地址")
        config_canoe_project_action.triggered.connect(self.config_canoe_project)
        canoe_menu.addAction(config_canoe_project_action)

        simulink_menu = project_menu.addMenu("Simulink(&S)")

        manage_simulink_files_action = QAction("配置工程文件(&M)...", self)
        manage_simulink_files_action.setStatusTip("配置Simulink工程文件")
        manage_simulink_files_action.triggered.connect(self.manage_simulink_files)
        simulink_menu.addAction(manage_simulink_files_action)

        scene_menu = project_menu.addMenu("Scene(&C)")

        add_scene_mapping_action = QAction("添加场景映射表(&A)...", self)
        add_scene_mapping_action.setStatusTip("添加场景映射表到项目")
        add_scene_mapping_action.triggered.connect(self.add_scene_mapping)
        scene_menu.addAction(add_scene_mapping_action)

        test_req_menu = project_menu.addMenu("Test Requirements(&T)")

        add_test_req_action = QAction("添加测试需求文档(&A)...", self)
        add_test_req_action.setStatusTip("添加测试需求文档到项目")
        add_test_req_action.triggered.connect(self.add_test_requirement)
        test_req_menu.addAction(add_test_req_action)

        # Automation 菜单
        automation_menu = project_menu.addMenu("Automation(&A)")

        set_preset_action = QAction("设置预设(&P)...", self)
        set_preset_action.setStatusTip("设置预设信号和场景")
        set_preset_action.triggered.connect(self.open_preset_setting)
        automation_menu.addAction(set_preset_action)

        template_setting_action = QAction("模板设置(&T)...", self)
        template_setting_action.setStatusTip("配置模板设置")
        template_setting_action.triggered.connect(self.open_template_setting)
        automation_menu.addAction(template_setting_action)

        ecu_record_action = QAction("配置ECU Record(&E)...", self)
        ecu_record_action.setStatusTip("Configure ECU Record settings")
        ecu_record_action.triggered.connect(self.open_ecu_record_config)
        automation_menu.addAction(ecu_record_action)

        # === 工具菜单 ===
        tools_menu = menubar.addMenu("工具(&T)")

        validate_action = QAction("验证Case(&V)", self)
        validate_action.setShortcut(QKeySequence("F5"))
        validate_action.setStatusTip("验证当前Case的格式")
        validate_action.triggered.connect(self.validate_case)
        tools_menu.addAction(validate_action)

        tools_menu.addSeparator()

        ai_assistant_action = QAction("AI助手(&A)...", self)
        ai_assistant_action.setStatusTip("打开AI助手对话框")
        ai_assistant_action.triggered.connect(self.open_ai_assistant)
        tools_menu.addAction(ai_assistant_action)

        dbc_converter_action = QAction("DBC转换器(&C)...", self)
        dbc_converter_action.setStatusTip("打开DBC转换器对话框")
        dbc_converter_action.triggered.connect(self.open_dbc_converter)
        tools_menu.addAction(dbc_converter_action)

        oss_config_action = QAction("OSS配置(&O)...", self)
        oss_config_action.setStatusTip("配置OSS存储")
        oss_config_action.triggered.connect(self.open_oss_config)
        tools_menu.addAction(oss_config_action)

        canoe_panel_action = QAction("CANoe面板生成(&P)...", self)
        canoe_panel_action.setStatusTip("生成CANoe面板文件")
        canoe_panel_action.triggered.connect(self.open_canoe_panel_generator)
        tools_menu.addAction(canoe_panel_action)

        canoe_capl_action = QAction("CANoe仿真节点CAPL生成(&C)...", self)
        canoe_capl_action.setStatusTip("生成CANoe仿真节点CAPL文件")
        canoe_capl_action.triggered.connect(self.open_canoe_capl_generator)
        tools_menu.addAction(canoe_capl_action)

        # === 帮助菜单 ===
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)...", self)
        about_action.setStatusTip("关于本程序")
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_toolbar(self) -> None:
        """初始化工具栏"""
        toolbar = QToolBar("主工具栏", self)
        self.addToolBar(toolbar)

        for label, handler in [
            ("新建项目", self.new_project),
            ("打开项目", self.open_project),
            ("保存项目", self.save_project),
        ]:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

        toolbar.addSeparator()

        for label, handler in [
            ("新建Case", self.new_case),
            ("保存Case", self.save_case),
        ]:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

        toolbar.addSeparator()

        for label, handler in [
            ("验证", self.validate_case),
            ("AI助手", self.open_ai_assistant),
        ]:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

    def init_statusbar(self) -> None:
        """初始化状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel("就绪")
        # 防御性约束：状态栏 label 不限宽时，长文本会把窗口最小宽度撑到上万像素
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(600)
        self.statusbar.addWidget(self.status_label, 1)
        self.project_label = QLabel("未打开项目")
        self.statusbar.addPermanentWidget(self.project_label)
        self.cursor_label = QLabel("行: 1, 列: 1")
        self.statusbar.addPermanentWidget(self.cursor_label)

    # ==================== 窗口状态 ====================

    def update_window_title(self) -> None:
        """更新窗口标题"""
        title = "HIL TEST"
        if self.project_manager.is_project_open():
            project_name = self.project_manager.get_project_name()
            title += f" - {project_name}"
            if self.current_case_name:
                title += f" - {self.current_case_name}"
                if self.current_case_modified:
                    title += " *"
        self.setWindowTitle(title)

    def update_status(self, message: str) -> None:
        """更新状态栏消息"""
        self.status_label.setText(message)
        self.statusbar.showMessage(message, 3000)

    # ==================== 项目管理 ====================

    def load_recent_projects(self) -> None:
        """加载最近项目"""
        self.update_recent_menu()

    def update_recent_menu(self) -> None:
        """更新最近项目菜单"""
        self.recent_menu.clear()
        recent_projects = self.config_manager.get_recent_projects()
        if not recent_projects:
            no_recent_action = QAction("无最近项目", self)
            no_recent_action.setEnabled(False)
            self.recent_menu.addAction(no_recent_action)
        else:
            for project_path in recent_projects:
                action = QAction(project_path, self)
                action.triggered.connect(lambda checked, path=project_path: self.open_project_by_path(path))
                self.recent_menu.addAction(action)

    def new_project(self) -> None:
        """新建项目"""
        # 如果当前有打开的项目，先保存并关闭
        if self.project_manager.is_project_open():
            self._save_open_files_state()
            self._clear_file_watcher()
            self.editor_tabs.clear()
            self.current_case_name = None
            self.current_case_modified = False
            self.dbc_parser.clear()

        dialog = NewProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project_path = dialog.get_project_path()
            project_name = dialog.get_project_name()
            if self.project_manager.create_project(project_path, project_name):
                self.config_manager.add_recent_project(str(self.project_manager.get_project_path()))
                self.update_recent_menu()
                self.load_project_config()
                self._setup_file_watcher()
                self.update_project_tree()
                self.update_status(f"项目 '{project_name}' 创建成功")
                self.update_window_title()
            else:
                QMessageBox.critical(self, "错误", "创建项目失败")

    def open_project(self) -> None:
        """打开项目"""
        project_path = QFileDialog.getExistingDirectory(
            self, "选择项目目录",
            str(self.config_manager.get('default_project_dir', '.'))
        )
        if project_path:
            self.open_project_by_path(project_path)

    def open_project_by_path(self, project_path: str) -> None:
        """通过路径打开项目"""
        # 如果当前有打开的项目，先保存打开的文件信息并关闭
        if self.project_manager.is_project_open():
            self._save_open_files_state()
            self._clear_file_watcher()
            # 清空标签页
            self.editor_tabs.clear()
            self.current_case_name = None
            self.current_case_modified = False
            # 清空旧项目的 DBC 数据
            self.dbc_parser.clear()

        if self.project_manager.open_project(project_path):
            self.config_manager.add_recent_project(project_path)
            self.update_recent_menu()
            self.load_project_config()
            self._cleanup_missing_file_references()
            self._setup_file_watcher()
            self.update_project_tree()
            # 检查是否有上次打开的文件，询问用户是否恢复
            self._restore_open_files_state_with_prompt()
            self.update_status(f"项目 '{self.project_manager.get_project_name()}' 打开成功")
            self.update_window_title()
        else:
            QMessageBox.critical(self, "错误", "打开项目失败")

    def load_project_config(self) -> None:
        """加载项目配置"""
        for dbc_file in self.project_manager.get_dbc_files():
            full_path = self.project_manager.get_full_path(dbc_file)
            if full_path:
                self.dbc_parser.load_dbc_file(str(full_path), "normal")

        for env_dbc_file in self.project_manager.get_env_dbc_files():
            full_path = self.project_manager.get_full_path(env_dbc_file)
            if full_path:
                self.dbc_parser.load_dbc_file(str(full_path), "env")

        for sysvar_file in self.project_manager.get_system_variable_files():
            full_path = self.project_manager.get_full_path(sysvar_file)
            if full_path:
                self.dbc_parser.load_system_variables(str(full_path))

        # 获取映射并转换为绝对路径
        relative_mapping = self.project_manager.get_can_channel_mapping()
        absolute_mapping = {}
        for rel_path, info in relative_mapping.items():
            abs_path = self.project_manager.get_full_path(rel_path)
            if abs_path:
                absolute_mapping[str(abs_path)] = info
        self.dbc_parser.set_can_channel_mapping(absolute_mapping)
        self.update_all_editor_completions()

    def save_project(self) -> None:
        """保存项目（包含保存当前case）"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "没有打开的项目")
            return
        if self.current_case_modified:
            self.save_case()
        if self.project_manager.save_project():
            self.update_status("项目保存成功")
        else:
            QMessageBox.critical(self, "错误", "保存项目失败")

    def close_project(self) -> None:
        """关闭项目"""
        if not self.project_manager.is_project_open():
            return
        if self.current_case_modified:
            reply = QMessageBox.question(
                self, "确认", "当前Case有未保存的修改，是否保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_case()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.editor_tabs.clear()
        self.dbc_parser.clear()
        self.project_manager.close_project()
        self.current_case_name = None
        self.current_case_modified = False
        self.update_project_tree()
        self.update_status("项目已关闭")
        self.update_window_title()
        self._clear_file_watcher()

    # ==================== 打开文件状态保存/恢复 ====================

    def _save_open_files_state(self) -> None:
        """保存当前打开的文件状态到项目配置"""
        if not self.project_manager.is_project_open():
            return

        open_files = []
        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if tab_data and isinstance(tab_data, dict):
                file_key = tab_data.get("file_key")
                editor_type = tab_data.get("editor_type", "modular")
                if file_key:
                    # 保存文件信息和编辑器类型
                    open_files.append({
                        "file_key": file_key,
                        "editor_type": editor_type
                    })

        current_index = self.editor_tabs.currentIndex()

        config = self.project_manager.project_config
        config["ui_state"] = {
            "open_files": open_files,
            "current_tab_index": current_index if current_index >= 0 else 0
        }
        self.project_manager.save_project()

    def _restore_open_files_state(self) -> None:
        """从项目配置恢复上次打开的文件（不带提示）"""
        if not self.project_manager.is_project_open():
            return

        config = self.project_manager.project_config
        ui_state = config.get("ui_state", {})
        open_files = ui_state.get("open_files", [])
        current_tab_index = ui_state.get("current_tab_index", 0)

        for file_info in open_files:
            # 兼容旧格式（纯字符串）和新格式（字典）
            if isinstance(file_info, str):
                file_key = file_info
                editor_type = "modular"
            else:
                file_key = file_info.get("file_key", "")
                editor_type = file_info.get("editor_type", "modular")

            if not file_key:
                continue

            # 根据编辑器类型调用不同的打开方法
            if editor_type == "modular":
                # modular: file_key 格式为 "directory/case_name" 或 "case_name"
                if "/" in file_key:
                    parts = file_key.split("/")
                    directory = parts[0]
                    case_name = parts[1] if len(parts) > 1 else parts[0]
                else:
                    directory = ""
                    case_name = file_key
                self.open_case_modular_editor_with_directory(case_name, directory)

            elif editor_type == "text":
                # text: file_key 格式为 "directory/case_name" 或 "case_name"
                if "/" in file_key:
                    parts = file_key.split("/")
                    directory = parts[0]
                    case_name = parts[1] if len(parts) > 1 else parts[0]
                else:
                    directory = ""
                    case_name = file_key
                self.open_case_text_editor(case_name, directory)

            elif editor_type == "viewer":
                # viewer: file_key 格式为 "viewer:file_type:file_name"
                if file_key.startswith("viewer:"):
                    parts = file_key.split(":", 2)
                    if len(parts) >= 3:
                        file_type = parts[1]
                        file_name = parts[2]
                        self.open_file_viewer(file_name, file_type)

            elif editor_type == "automation":
                # automation: file_key 格式为 "automation:case_type:file_path"
                if file_key.startswith("automation:"):
                    parts = file_key.split(":", 2)
                    if len(parts) >= 3:
                        case_type = parts[1]
                        file_path = parts[2]
                        self.open_automation_file(file_path, case_type)

            elif editor_type == "test_results":
                # test_results: file_key is full file path
                # Determine file type by extension
                if file_key.endswith(".log"):
                    data_type = "log"
                elif file_key.endswith(".html"):
                    data_type = "report"
                else:
                    continue  # Skip unknown file types
                # Extract relative path from "Test Results/xxx data/" prefix
                try:
                    # Find the base directory for this data type
                    dir_name = self._DATA_TYPE_DIR_MAP.get(data_type, "trace data")
                    base_prefix = f"Test Results{os.sep}{dir_name}"
                    # Find position of base_prefix in file_key
                    pos = file_key.find(base_prefix)
                    if pos >= 0:
                        # Extract the part after base_prefix + separator
                        start_pos = pos + len(base_prefix)
                        # Skip leading separator if present
                        while start_pos < len(file_key) and file_key[start_pos] in (os.sep, '/', '\\'):
                            start_pos += 1
                        relative_path = file_key[start_pos:]
                        self.open_test_results_file(relative_path, data_type)
                except Exception:
                    pass  # Skip if path extraction fails

        # 恢复当前标签页索引
        if self.editor_tabs.count() > 0 and current_tab_index < self.editor_tabs.count():
            self.editor_tabs.setCurrentIndex(current_tab_index)

    def _restore_open_files_state_with_prompt(self) -> None:
        """从项目配置恢复上次打开的文件（带提示）"""
        if not self.project_manager.is_project_open():
            return

        config = self.project_manager.project_config
        ui_state = config.get("ui_state", {})
        open_files = ui_state.get("open_files", [])

        # 如果有上次打开的文件，询问用户是否恢复
        if open_files:
            file_count = len(open_files)
            reply = QMessageBox.question(
                self,
                "恢复标签页",
                f"上次在此项目中打开了 {file_count} 个文件，是否恢复这些标签页？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._restore_open_files_state()
            else:
                # 用户选择不恢复，清空保存的状态
                config["ui_state"] = {"open_files": [], "current_tab_index": 0}
                self.project_manager.save_project()

    # ==================== 文件监视器 ====================

    def _setup_file_watcher(self) -> None:
        """设置文件监视器，监听项目目录变化"""
        dirs = self._collect_watch_dirs()
        if dirs:
            self.file_watcher.addPaths(dirs)
            
    def _collect_watch_dirs(self) -> List[str]:
        """收集需要监视的目录（仅业务目录，过滤高噪声目录）"""
        if not self.project_manager.is_project_open():
            return []
        project_path = self.project_manager.current_project_path
        if not project_path:
            return []

        watch_root_dirs = [
            project_path / "CANoe" / "dbc_file",
            project_path / "CANoe" / "env_dbc",
            project_path / "CANoe" / "system_variable",
            project_path / "CANoe" / "panel_files",
            project_path / "dsl_case",
            project_path / "Scene",
            project_path / "TestRequirements",
            project_path / "automation_case" / "py_cases",
            project_path / "automation_case" / "json_cases",
            project_path / "Test Results" / "trace data",
            project_path / "Test Results" / "record data",
            project_path / "Test Results" / "log data",
            project_path / "Test Results" / "report data",
        ]

        excluded_dir_names = {
            ".git", "__pycache__", ".idea", ".vscode", ".pytest_cache", "node_modules"
        }

        all_dirs: List[str] = []
        seen = set()

        for root_path in watch_root_dirs:
            if not root_path.exists():
                continue

            for current_root, dirnames, _ in os.walk(root_path):
                dirnames[:] = [d for d in dirnames if d not in excluded_dir_names]
                if current_root not in seen:
                    seen.add(current_root)
                    all_dirs.append(current_root)

        return all_dirs
    
    def _sync_file_watcher(self) -> None:
        """增量同步文件监视器：添加新目录，移除已删除/失效目录"""
        desired = set(self._collect_watch_dirs())
        current_dirs = set(self.file_watcher.directories())
        current_files = set(self.file_watcher.files())

        stale_dirs = {p for p in current_dirs if not Path(p).exists()}
        stale_files = {p for p in current_files if not Path(p).exists()}

        to_remove = (current_dirs - desired) | stale_dirs | stale_files
        valid_current_dirs = current_dirs - stale_dirs
        to_add = desired - valid_current_dirs

        if to_remove:
            self.file_watcher.removePaths(list(to_remove))
        if to_add:
            self.file_watcher.addPaths(list(to_add))

    def _clear_file_watcher(self) -> None:
        """清除文件监视器"""
        dirs = self.file_watcher.directories()
        files = self.file_watcher.files()
        if dirs:
            self.file_watcher.removePaths(dirs)
        if files:
            self.file_watcher.removePaths(files)
            
    def _remove_watch_paths_under(self, root_path: Path) -> None:
        """移除 root_path 及其子路径的 watcher 注册，避免 Windows 删除时报权限告警"""
        try:
            root_norm = os.path.normcase(os.path.normpath(str(root_path)))
            root_prefix = root_norm + os.sep

            to_remove: List[str] = []

            for p in list(self.file_watcher.directories()):
                p_norm = os.path.normcase(os.path.normpath(p))
                if p_norm == root_norm or p_norm.startswith(root_prefix):
                    to_remove.append(p)

            for p in list(self.file_watcher.files()):
                p_norm = os.path.normcase(os.path.normpath(p))
                if p_norm == root_norm or p_norm.startswith(root_prefix):
                    to_remove.append(p)

            if to_remove:
                self.file_watcher.removePaths(list(dict.fromkeys(to_remove)))
        except Exception:
            pass

    def on_directory_changed(self, path: str) -> None:
        """目录变化：防抖合并，降低滚动过程中的刷新抢占"""
        self._last_fs_event_time = time.monotonic()
        self._pending_tree_refresh = True
        debounce_ms = int(getattr(self, "_dir_change_debounce_ms", 420))
        self._refresh_timer.start(debounce_ms)

    def on_file_changed(self, path: str) -> None:
        """文件变化：更长防抖，避免滚轮后立即重建树"""
        self._last_fs_event_time = time.monotonic()
        self._pending_tree_refresh = True
        debounce_ms = int(getattr(self, "_file_change_debounce_ms", 600))
        self._refresh_timer.start(debounce_ms)

    def _do_refresh_project_tree(self) -> None:
        """执行项目树刷新：交互结束并稳定后再刷新，减少抖动"""
        if not self.project_manager.is_project_open():
            return

        if not getattr(self, "_pending_tree_refresh", False):
            return

        now = time.monotonic()
        retry_ms = int(getattr(self, "_tree_retry_ms", 150))
        wheel_quiet_sec = float(getattr(self, "_tree_wheel_quiet_sec", 0.72))
        fs_settle_sec = float(getattr(self, "_tree_fs_settle_sec", 0.30))

        if self.project_tree._mouse_pressed:
            self._refresh_timer.start(retry_ms)
            return

        if self.project_tree.verticalScrollBar().isSliderDown():
            self._refresh_timer.start(retry_ms)
            return

        # 若历史版本存在平滑滚动动画，也等待其结束
        smooth_timer = getattr(self.project_tree, "_smooth_scroll_timer", None)
        if smooth_timer is not None and smooth_timer.isActive():
            self._refresh_timer.start(retry_ms)
            return

        if now - self.project_tree._last_wheel_time < wheel_quiet_sec:
            self._refresh_timer.start(retry_ms)
            return

        if now - getattr(self, "_last_fs_event_time", 0.0) < fs_settle_sec:
            self._refresh_timer.start(retry_ms)
            return

        self._pending_tree_refresh = False
        self._cleanup_missing_file_references()
        self._sync_canoe_files_from_disk()
        self.project_manager.sync_test_results()
        self.update_project_tree()
        self._sync_file_watcher()
    
    def _cleanup_missing_file_references(self) -> None:
        """清理项目中已不存在的文件引用"""
        if not self.project_manager.is_project_open():
            return
        project_path = self.project_manager.current_project_path
        if not project_path:
            return

        config_changed = False
        cfg = self.project_manager.project_config

        def _resolve_and_check(file_path: str) -> bool:
            """检查文件路径是否存在"""
            if not file_path:
                return True
            full = Path(file_path) if Path(file_path).is_absolute() else project_path / file_path
            return full.exists()

        # 清理 dict 列表类型（含 "file" 键）
        for key in ("test_requirements", "scene_mappings", "dsl_cases"):
            items = cfg.get(key, [])
            valid = []
            for item in items:
                if _resolve_and_check(item.get("file", "")):
                    valid.append(item)
                else:
                    config_changed = True
            cfg[key] = valid

        # 清理CANoe相关文件
        dbc_needs_refresh = False
        canoe_cfg = cfg.get("canoe", {})

        # 清理DBC文件（字典格式，键为 CAN 1, CAN 2 等）
        dbc_files = canoe_cfg.get("dbc_files", {})
        if isinstance(dbc_files, dict):
            keys_to_remove = []
            for can_key, file_info in dbc_files.items():
                path_str = file_info.get("path", "") if isinstance(file_info, dict) else ""
                if path_str and not _resolve_and_check(path_str):
                    # 文件不存在，从配置中移除
                    full_path = Path(path_str) if Path(path_str).is_absolute() else project_path / path_str
                    self.dbc_parser.unload_dbc_file(str(full_path))
                    keys_to_remove.append(can_key)
                    config_changed = True
                    dbc_needs_refresh = True
            for key in keys_to_remove:
                del dbc_files[key]
        elif isinstance(dbc_files, list):
            # 兼容旧格式（列表）
            valid = []
            for path_str in dbc_files:
                if _resolve_and_check(path_str):
                    valid.append(path_str)
                else:
                    full_path = Path(path_str) if Path(path_str).is_absolute() else project_path / path_str
                    self.dbc_parser.unload_dbc_file(str(full_path))
                    config_changed = True
                    dbc_needs_refresh = True
            canoe_cfg["dbc_files"] = valid

        # 清理环境变量DBC文件（列表格式）
        env_dbc_files = canoe_cfg.get("env_dbc_files", [])
        valid = []
        for path_str in env_dbc_files:
            if _resolve_and_check(path_str):
                valid.append(path_str)
            else:
                full_path = Path(path_str) if Path(path_str).is_absolute() else project_path / path_str
                self.dbc_parser.unload_dbc_file(str(full_path))
                config_changed = True
                dbc_needs_refresh = True
        if len(valid) != len(env_dbc_files):
            canoe_cfg["env_dbc_files"] = valid

        # 清理系统变量文件（列表格式）
        sysvar_files = canoe_cfg.get("system_variable_files", [])
        valid = []
        for path_str in sysvar_files:
            if _resolve_and_check(path_str):
                valid.append(path_str)
            else:
                full_path = Path(path_str) if Path(path_str).is_absolute() else project_path / path_str
                self.dbc_parser.remove_system_variables(str(full_path))
                config_changed = True
                dbc_needs_refresh = True
        if len(valid) != len(sysvar_files):
            canoe_cfg["system_variable_files"] = valid

        # 清理CAN通道映射中不存在的文件引用
        can_channel_mapping = canoe_cfg.get("can_channel_mapping", {})
        keys_to_remove = []
        for path_str in can_channel_mapping.keys():
            if not _resolve_and_check(path_str):
                keys_to_remove.append(path_str)
                config_changed = True
        for key in keys_to_remove:
            del can_channel_mapping[key]

        # 清理面板文件（列表格式）
        panel_files = canoe_cfg.get("panel_files", [])
        valid = []
        for panel_info in panel_files:
            path_str = panel_info.get("path", "") if isinstance(panel_info, dict) else panel_info
            if _resolve_and_check(path_str):
                valid.append(panel_info)
            else:
                config_changed = True
        if len(valid) != len(panel_files):
            canoe_cfg["panel_files"] = valid

        if config_changed:
            self.project_manager.save_project()

        if dbc_needs_refresh:
            self.update_all_editor_completions()

    def _sync_canoe_files_from_disk(self) -> None:
        """同步外部新增的CANoe文件到项目配置"""
        if not self.project_manager.is_project_open():
            return
        project_path = self.project_manager.current_project_path
        if not project_path:
            return

        cfg = self.project_manager.project_config
        if "canoe" not in cfg:
            cfg["canoe"] = {}

        config_changed = False
        dbc_needs_refresh = False

        # 同步DBC文件
        dbc_dir = project_path / "CANoe" / "dbc_file"
        if dbc_dir.exists():
            existing_paths = set()
            dbc_files = cfg["canoe"].get("dbc_files", {})
            if isinstance(dbc_files, list):
                # 旧格式：列表形式
                existing_paths = set(dbc_files)
            else:
                # 新格式：字典形式，键可能是相对路径或 "CAN X" 格式
                # 需要从字典的值中提取 path 字段来判断
                for key, value in dbc_files.items():
                    if isinstance(value, dict):
                        # 统一路径分隔符进行比较
                        path = value.get("path", key)
                        existing_paths.add(path.replace("\\", "/"))
                    else:
                        existing_paths.add(key.replace("\\", "/"))

            for dbc_file in dbc_dir.glob("*.dbc"):
                relative_path = f"CANoe/dbc_file/{dbc_file.name}"
                if relative_path not in existing_paths:
                    # 新文件，添加到配置
                    if isinstance(dbc_files, list):
                        dbc_files.append(relative_path)
                    else:
                        # 找一个未使用的 CAN 通道键
                        used_channels = set()
                        for key, value in dbc_files.items():
                            if key.startswith("CAN "):
                                try:
                                    used_channels.add(int(key.split()[1]))
                                except (ValueError, IndexError):
                                    pass
                        new_channel = 1
                        while new_channel in used_channels:
                            new_channel += 1
                        can_key = f"CAN {new_channel}"
                        dbc_files[can_key] = {
                            "path": relative_path,
                            "short_name": "",
                            "channel": new_channel - 1
                        }
                    config_changed = True
                    dbc_needs_refresh = True
                    # 加载到解析器
                    self.dbc_parser.load_dbc_file(str(dbc_file))

            cfg["canoe"]["dbc_files"] = dbc_files

        # 同步环境变量DBC文件
        env_dbc_dir = project_path / "CANoe" / "env_dbc"
        if env_dbc_dir.exists():
            # 统一路径分隔符进行比较
            existing_paths = set(p.replace("\\", "/") for p in cfg["canoe"].get("env_dbc_files", []))

            for env_file in env_dbc_dir.glob("*.dbc"):
                relative_path = f"CANoe/env_dbc/{env_file.name}"
                if relative_path not in existing_paths:
                    if "env_dbc_files" not in cfg["canoe"]:
                        cfg["canoe"]["env_dbc_files"] = []
                    cfg["canoe"]["env_dbc_files"].append(relative_path)
                    config_changed = True
                    dbc_needs_refresh = True
                    # 加载到解析器
                    self.dbc_parser.load_dbc_file(str(env_file))

        # 同步系统变量文件
        sysvar_dir = project_path / "CANoe" / "system_variable"
        if sysvar_dir.exists():
            # 统一路径分隔符进行比较
            existing_paths = set(p.replace("\\", "/") for p in cfg["canoe"].get("system_variable_files", []))

            # 支持多种系统变量文件格式
            for ext in ["*.xml", "*.vsysvar"]:
                for sysvar_file in sysvar_dir.glob(ext):
                    relative_path = f"CANoe/system_variable/{sysvar_file.name}"
                    if relative_path not in existing_paths:
                        if "system_variable_files" not in cfg["canoe"]:
                            cfg["canoe"]["system_variable_files"] = []
                        cfg["canoe"]["system_variable_files"].append(relative_path)
                        config_changed = True
                        dbc_needs_refresh = True
                        # 加载到解析器
                        self.dbc_parser.load_system_variables(str(sysvar_file))

        # 同步面板文件
        panel_dir = project_path / "CANoe" / "panel_files"
        if panel_dir.exists():
            existing_panel_names = set()
            panel_files = cfg["canoe"].get("panel_files", [])
            for panel_info in panel_files:
                if isinstance(panel_info, dict):
                    existing_panel_names.add(panel_info.get("name", ""))
                else:
                    existing_panel_names.add(Path(panel_info).name)

            for panel_file in panel_dir.glob("*.xvp"):
                if panel_file.name not in existing_panel_names:
                    relative_path = f"CANoe/panel_files/{panel_file.name}"
                    # 从文件名解析namespace和message信息
                    # 文件名格式: {namespace}_{node}_{message}_panel.xvp
                    parts = panel_file.stem.replace("_panel", "").split("_")
                    namespace = parts[0] if len(parts) > 0 else ""
                    message_name = parts[-1] if len(parts) > 1 else ""

                    if "panel_files" not in cfg["canoe"]:
                        cfg["canoe"]["panel_files"] = []
                    cfg["canoe"]["panel_files"].append({
                        "name": panel_file.name,
                        "path": relative_path,
                        "namespace": namespace,
                        "message_name": message_name,
                        "created_time": datetime.now().isoformat()
                    })
                    config_changed = True

        if config_changed:
            self.project_manager.save_project()

        if dbc_needs_refresh:
            self.update_all_editor_completions()

    # ==================== 项目树 ====================

    def update_project_tree(self, *, restore_selection: bool = True) -> None:
        """更新项目树，restore_selection=False 时不恢复之前的选中状态"""

        saved_expanded = self._save_expanded_state()
        saved_current_data = None
        saved_selections: List[Dict[str, Any]] = []
        saved_scroll = self.project_tree.verticalScrollBar().value()

        if restore_selection:
            current_item = self.project_tree.currentItem()
            if current_item:
                saved_current_data = current_item.data(0, Qt.ItemDataRole.UserRole)
            saved_selections = self._save_selected_items()

        self.project_tree.setUpdatesEnabled(False)
        self.project_tree.clear()

        if not self.project_manager.is_project_open():
            self.project_tree.setUpdatesEnabled(True)
            return

        self.project_manager.sync_dsl_cases()
        self.project_manager.sync_automation_cases()
        self.project_manager.sync_test_results()

        project_name = self.project_manager.get_project_name()
        root_item = QTreeWidgetItem(self.project_tree, [project_name])
        root_item.setExpanded(True)

        # CANoe
        canoe_item = QTreeWidgetItem(root_item, ["CANoe"])
        canoe_item.setExpanded(True)

        dbc_item = QTreeWidgetItem(canoe_item, ["DBC文件"])
        dbc_item.setExpanded(True)
        for dbc_file in self.project_manager.get_dbc_files():
            QTreeWidgetItem(dbc_item, [Path(dbc_file).name])

        env_dbc_item = QTreeWidgetItem(canoe_item, ["环境变量DBC文件"])
        env_dbc_item.setExpanded(True)
        for env_dbc_file in self.project_manager.get_env_dbc_files():
            QTreeWidgetItem(env_dbc_item, [Path(env_dbc_file).name])

        sysvar_item = QTreeWidgetItem(canoe_item, ["系统变量文件"])
        sysvar_item.setExpanded(True)
        for sysvar_file in self.project_manager.get_system_variable_files():
            QTreeWidgetItem(sysvar_item, [Path(sysvar_file).name])

        # CANoe面板文件
        canoe_panel_dir = self.project_manager.get_panel_dir()
        if canoe_panel_dir and canoe_panel_dir.exists():
            panel_item = QTreeWidgetItem(canoe_item, ["面板文件"])
            panel_item.setExpanded(True)
            # 遍历目录中的.xvp文件
            for panel_file in canoe_panel_dir.glob("*.xvp"):
                QTreeWidgetItem(panel_item, [panel_file.name])

        canoe_project_path = self.project_manager.get_canoe_project_path()
        if canoe_project_path:
            project_file_item = QTreeWidgetItem(canoe_item, ["工程文件"])
            project_file_item.setExpanded(True)
            QTreeWidgetItem(project_file_item, [Path(canoe_project_path).name])

        # Simulink
        simulink_item = QTreeWidgetItem(root_item, ["Simulink"])
        simulink_item.setExpanded(True)
        simulink_files = self.project_manager.get_simulink_files()
        if simulink_files:
            files_item = QTreeWidgetItem(simulink_item, ["工程文件"])
            files_item.setExpanded(True)
            for file_info in simulink_files:
                QTreeWidgetItem(files_item, [file_info["name"]])

        # DSL Cases
        case_item = QTreeWidgetItem(root_item, ["DSL Cases"])
        case_item.setExpanded(True)
        dir_structure = self.project_manager.get_dsl_directory_structure()
        if dir_structure:
            self._build_dsl_tree(case_item, dir_structure)
        else:
            for case_info in self.project_manager.get_dsl_cases():
                file_path = case_info.get("file", "")
                if file_path:
                    QTreeWidgetItem(case_item, [Path(file_path).name])
                else:
                    QTreeWidgetItem(case_item, [case_info["name"]])

        # Scene
        scene_item = QTreeWidgetItem(root_item, ["Scene"])
        scene_item.setExpanded(True)
        for mapping_info in self.project_manager.get_scene_mappings():
            QTreeWidgetItem(scene_item, [mapping_info["name"]])

        # Test Requirements
        test_req_item = QTreeWidgetItem(root_item, ["Test Requirements"])
        test_req_item.setExpanded(True)
        for req_info in self.project_manager.get_test_requirements():
            QTreeWidgetItem(test_req_item, [req_info["name"]])

        # Automation Cases
        automation_item = QTreeWidgetItem(root_item, ["Automation Cases"])
        automation_item.setExpanded(True)

        py_cases_item = QTreeWidgetItem(automation_item, ["py_cases"])
        py_cases_item.setExpanded(True)
        py_structure = self.project_manager.get_automation_directory_structure("py_cases")
        if py_structure:
            self._build_automation_tree(py_cases_item, py_structure, "py")

        json_cases_item = QTreeWidgetItem(automation_item, ["json_cases"])
        json_cases_item.setExpanded(True)
        json_structure = self.project_manager.get_automation_directory_structure("json_cases")
        if json_structure:
            self._build_automation_tree(json_cases_item, json_structure, "json")

        # Test Results
        test_results_item = QTreeWidgetItem(root_item, ["Test Results"])
        test_results_item.setExpanded(True)

        trace_data_item = QTreeWidgetItem(test_results_item, ["trace data"])
        trace_data_item.setExpanded(True)
        trace_structure = self.project_manager.get_test_results_directory_structure("trace_data")
        if trace_structure:
            self._build_test_results_tree(trace_data_item, trace_structure, "trace")

        record_data_item = QTreeWidgetItem(test_results_item, ["record data"])
        record_data_item.setExpanded(True)
        record_structure = self.project_manager.get_test_results_directory_structure("record_data")
        if record_structure:
            self._build_test_results_tree(record_data_item, record_structure, "record")

        log_data_item = QTreeWidgetItem(test_results_item, ["log data"])
        log_data_item.setExpanded(True)
        log_structure = self.project_manager.get_test_results_directory_structure("log_data")
        if log_structure:
            self._build_test_results_tree(log_data_item, log_structure, "log")

        report_data_item = QTreeWidgetItem(test_results_item, ["report data"])
        report_data_item.setExpanded(True)
        report_structure = self.project_manager.get_test_results_directory_structure("report_data")
        if report_structure:
            self._build_test_results_tree(report_data_item, report_structure, "report")

        if saved_expanded:
            self._restore_expanded_state(saved_expanded)
        self._restore_selected_items(saved_selections)

        current_restored = False
        if saved_current_data:
            root = self.project_tree.invisibleRootItem()
            found = self._find_tree_item_by_data(root, saved_current_data)
            if found:
                self.project_tree.setCurrentItem(
                    found, 0, QItemSelectionModel.SelectionFlag.Current
                )
                current_restored = True

        if not current_restored:
            fallback = None
            selected = self.project_tree.selectedItems()
            if selected:
                fallback = selected[0]
            else:
                top = self.project_tree.topLevelItem(0)
                if top and top.childCount() > 0:
                    fallback = top.child(0)
            if fallback:
                self.project_tree.setCurrentItem(
                    fallback, 0, QItemSelectionModel.SelectionFlag.Current
                )

        self.project_tree.setUpdatesEnabled(True)
        line_h = max(self.project_tree.fontMetrics().height(), 20)
        self.project_tree.verticalScrollBar().setSingleStep(line_h)
        self.project_tree.verticalScrollBar().setValue(saved_scroll)

    # ==================== 树状态保存/恢复 ====================

    def _get_node_key(self, item: QTreeWidgetItem) -> str:
        """生成树节点的唯一标识键"""
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if item_data:
            return f"data:{item_data.get('type', '')}:{item_data.get('path', '')}:{item_data.get('case_type', '')}"
        parts = []
        current = item
        while current:
            parts.insert(0, current.text(0))
            current = current.parent()
        return "text:" + "/".join(parts)

    def _save_expanded_state(self) -> Dict[str, bool]:
        """保存所有树节点的展开/折叠状态"""
        state: Dict[str, bool] = {}
        root = self.project_tree.invisibleRootItem()
        self._collect_expanded_state(root, state)
        return state

    def _collect_expanded_state(self, parent: QTreeWidgetItem, state: Dict[str, bool]) -> None:
        for i in range(parent.childCount()):
            item = parent.child(i)
            if item.childCount() > 0:
                key = self._get_node_key(item)
                state[key] = item.isExpanded()
            self._collect_expanded_state(item, state)

    def _restore_expanded_state(self, state: Dict[str, bool]) -> None:
        """恢复树节点的展开/折叠状态"""
        root = self.project_tree.invisibleRootItem()
        self._apply_expanded_state(root, state)

    def _apply_expanded_state(self, parent: QTreeWidgetItem, state: Dict[str, bool]) -> None:
        for i in range(parent.childCount()):
            item = parent.child(i)
            key = self._get_node_key(item)
            if key in state:
                item.setExpanded(state[key])
            self._apply_expanded_state(item, state)

    def _save_selected_items(self) -> List[Dict[str, Any]]:
        """保存所有选中节点的标识数据"""
        selected_data = []
        for item in self.project_tree.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                selected_data.append(dict(data))
        return selected_data

    def _restore_selected_items(self, selected_data: List[Dict[str, Any]]) -> None:
        """恢复多选状态"""
        if not selected_data:
            return
        root = self.project_tree.invisibleRootItem()
        for data in selected_data:
            found = self._find_tree_item_by_data(root, data)
            if found:
                found.setSelected(True)

    def _build_dsl_tree(self, parent_item: QTreeWidgetItem, node: Dict[str, Any]) -> None:
        """递归构建 DSL 目录树，只接受 .dsl 文件"""
        if not node["name"]:
            for child in node.get("children", []):
                self._build_dsl_tree(parent_item, child)
            return
 
        if node["type"] == "directory":
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "directory", "path": node["path"]})
            item.setExpanded(True)
            for child in node.get("children", []):
                self._build_dsl_tree(item, child)
        else:
            if not node["name"].endswith(".dsl"):
                return
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": node["path"]})
    
    def _build_automation_tree(self, parent_item: QTreeWidgetItem, node: Dict[str, Any], case_type: str) -> None:
        """递归构建 Automation Cases 目录树，py_cases 只接受 .py，json_cases 只接受 .json"""
        self._AUTOMATION_SUFFIX = {"py": ".py", "json": ".json"}
        
        if not node["name"]:
            for child in node.get("children", []):
                self._build_automation_tree(parent_item, child, case_type)
            return
 
        if node["type"] == "directory":
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "automation_directory", "path": node["path"], "case_type": case_type
            })
            item.setExpanded(True)
            for child in node.get("children", []):
                self._build_automation_tree(item, child, case_type)
        else:
            required_suffix = self._AUTOMATION_SUFFIX.get(case_type)
            if required_suffix and not node["name"].endswith(required_suffix):
                return
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "automation_file", "path": node["path"], "case_type": case_type
            })

    def _build_test_results_tree(self, parent_item: QTreeWidgetItem, node: Dict[str, Any], data_type: str) -> None:
        """递归构建 Test Results 目录树"""
        _TEST_RESULTS_SUFFIX = {
            "trace": ".blf",
            "record": ".record",
            "log": ".log",
            "report": ".html"
        }

        if not node["name"]:
            for child in node.get("children", []):
                self._build_test_results_tree(parent_item, child, data_type)
            return

        if node["type"] == "directory":
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "test_results_directory", "path": node["path"], "data_type": data_type
            })
            item.setExpanded(True)
            for child in node.get("children", []):
                self._build_test_results_tree(item, child, data_type)
        else:
            required_suffix = _TEST_RESULTS_SUFFIX.get(data_type)
            if required_suffix and not node["name"].endswith(required_suffix):
                return
            item = QTreeWidgetItem(parent_item, [node["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "test_results_file", "path": node["path"], "data_type": data_type
            })

    def _restore_tree_item_by_data(self, item_data: Dict[str, Any]) -> bool:
        """根据节点的 UserRole 数据恢复树当前项（不清除已有选中状态），返回是否成功"""
        root = self.project_tree.invisibleRootItem()
        found = self._find_tree_item_by_data(root, item_data)
        if found:
            self.project_tree.setCurrentItem(found, 0, QItemSelectionModel.SelectionFlag.Current)
            self.project_tree.scrollToItem(found)
            return True
        return False

    def _find_tree_item_by_data(self, parent: QTreeWidgetItem, target_data: Dict[str, Any]) -> Optional[QTreeWidgetItem]:
        """递归查找具有匹配 UserRole 数据的树节点"""
        for i in range(parent.childCount()):
            item = parent.child(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data == target_data:
                return item
            result = self._find_tree_item_by_data(item, target_data)
            if result:
                return result
        return None

    # ==================== 标签切换与树节点高亮 ====================

    def on_tab_changed(self, index: int) -> None:
        """标签切换事件 - 高亮对应的树节点"""
        if index < 0:
            return
        tab_data = self.editor_tabs.tabBar().tabData(index)
        if not tab_data or not isinstance(tab_data, dict):
            return
        file_key = tab_data.get("file_key")
        if not file_key:
            return

        if file_key.startswith("automation:"):
            parts = file_key.split(":", 2)
            if len(parts) >= 3:
                self._highlight_automation_node(parts[2], parts[1])
            return

        if file_key.startswith("viewer:"):
            parts = file_key.split(":", 2)
            if len(parts) >= 3:
                self._highlight_viewer_node(parts[2], parts[1])
            return

        if "/" in file_key:
            parts = file_key.split("/")
            case_name = parts[-1]
            directory = "/".join(parts[:-1])
        else:
            case_name = file_key
            directory = ""

        self._highlight_tree_node(case_name, directory)

    def _highlight_automation_node(self, file_path: str, case_type: str) -> None:
        """在项目树中高亮对应的 Automation Cases 节点"""
        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "Automation Cases":
                    for k in range(child.childCount()):
                        cases_item = child.child(k)
                        cases_type = "py" if cases_item.text(0) == "py_cases" else "json" if cases_item.text(0) == "json_cases" else None
                        if cases_type == case_type:
                            self._find_and_highlight_automation_node(cases_item, file_path)
                            return

    def _find_and_highlight_automation_node(self, parent: QTreeWidgetItem, file_path: str) -> bool:
        """递归查找并高亮 Automation Cases 节点"""
        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "automation_file":
                if item_data.get("path", "") == file_path:
                    self.project_tree.setCurrentItem(item)
                    self.project_tree.scrollToItem(item)
                    return True
            elif item_data and item_data.get("type") == "automation_directory":
                if self._find_and_highlight_automation_node(item, file_path):
                    return True
        return False

    def _highlight_automation_directory_node(self, dir_path: str, case_type: str) -> None:
        """在项目树中高亮对应的 Automation Cases 目录节点"""
        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "Automation Cases":
                    for k in range(child.childCount()):
                        cases_item = child.child(k)
                        cases_type = "py" if cases_item.text(0) == "py_cases" else "json" if cases_item.text(0) == "json_cases" else None
                        if cases_type == case_type:
                            self._find_and_highlight_automation_dir_node(cases_item, dir_path)
                            return

    def _find_and_highlight_automation_dir_node(self, parent: QTreeWidgetItem, dir_path: str) -> bool:
        """递归查找并高亮 Automation Cases 目录节点"""
        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "automation_directory":
                if item_data.get("path", "") == dir_path:
                    self.project_tree.setCurrentItem(item)
                    self.project_tree.scrollToItem(item)
                    return True
                if self._find_and_highlight_automation_dir_node(item, dir_path):
                    return True
        return False

    def _highlight_test_results_node(self, file_path: str, data_type: str) -> None:
        """在项目树中高亮对应的 Test Results 文件节点"""
        # Data type to tree item text mapping
        DATA_TYPE_TREE_MAP = {
            "trace": "trace data",
            "record": "record data",
            "log": "log data",
            "report": "report data"
        }

        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "Test Results":
                    for k in range(child.childCount()):
                        data_item = child.child(k)
                        tree_text = data_item.text(0)
                        item_type = DATA_TYPE_TREE_MAP.get(data_type)
                        if tree_text == item_type:
                            self._find_and_highlight_test_results_node(data_item, file_path)
                            return

    def _find_and_highlight_test_results_node(self, parent: QTreeWidgetItem, file_path: str) -> bool:
        """递归查找并高亮 Test Results 文件节点"""
        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "test_results_file":
                if item_data.get("path", "") == file_path:
                    self.project_tree.setCurrentItem(item)
                    self.project_tree.scrollToItem(item)
                    return True
            elif item_data and item_data.get("type") == "test_results_directory":
                if self._find_and_highlight_test_results_node(item, file_path):
                    return True
        return False

    def _highlight_test_results_directory_node(self, dir_path: str, data_type: str) -> None:
        """在项目树中高亮对应的 Test Results 目录节点"""
        # Data type to tree item text mapping
        DATA_TYPE_TREE_MAP = {
            "trace": "trace data",
            "record": "record data",
            "log": "log data",
            "report": "report data"
        }

        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "Test Results":
                    for k in range(child.childCount()):
                        data_item = child.child(k)
                        tree_text = data_item.text(0)
                        item_type = DATA_TYPE_TREE_MAP.get(data_type)
                        if tree_text == item_type:
                            self._find_and_highlight_test_results_dir_node(data_item, dir_path)
                            return

    def _find_and_highlight_test_results_dir_node(self, parent: QTreeWidgetItem, dir_path: str) -> bool:
        """递归查找并高亮 Test Results 目录节点"""
        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "test_results_directory":
                if item_data.get("path", "") == dir_path:
                    self.project_tree.setCurrentItem(item)
                    self.project_tree.scrollToItem(item)
                    return True
                if self._find_and_highlight_test_results_dir_node(item, dir_path):
                    return True
        return False

    def _highlight_viewer_node(self, file_name: str, file_type: str) -> None:
        """在项目树中高亮对应的 CANoe/Simulink 等查看器节点"""
        _TYPE_TO_PARENT = {
            "CANoe/dbc_file": "DBC文件",
            "CANoe/env_dbc": "环境变量DBC文件",
            "CANoe/system_variable": "系统变量文件",
        }
        parent_text = _TYPE_TO_PARENT.get(file_type)
        if not parent_text:
            return
        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                section = project_item.child(j)
                if section.text(0) == "CANoe":
                    for k in range(section.childCount()):
                        category = section.child(k)
                        if category.text(0) == parent_text:
                            for m in range(category.childCount()):
                                child = category.child(m)
                                if child.text(0) == file_name:
                                    self.project_tree.setCurrentItem(child)
                                    self.project_tree.scrollToItem(child)
                                    return
                    return

    def _highlight_tree_node(self, case_name: str, directory: str) -> None:
        """在项目树中高亮对应的 DSL 节点"""
        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "DSL Cases":
                    self._find_and_highlight_node(child, case_name, directory, 0)
                    return

    def _find_and_highlight_node(self, parent: QTreeWidgetItem, case_name: str, directory: str, depth: int = 0) -> bool:
        """递归查找并高亮 DSL 节点"""
        if depth > 20:
            return False

        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)

            if item_data and item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path.endswith('.dsl'):
                    item_case_name = Path(file_path).stem
                    item_parent = PurePosixPath(file_path).parent
                    item_directory = str(item_parent) if str(item_parent) != "." else ""
                    if item_case_name == case_name and item_directory == directory:
                        self.project_tree.setCurrentItem(item)
                        self.project_tree.scrollToItem(item)
                        return True
            elif item_data and item_data.get("type") == "directory":
                if self._find_and_highlight_node(item, case_name, directory, depth + 1):
                    return True
        return False

    def _highlight_directory_node(self, directory_name: str, parent_directory: str) -> None:
        """在项目树中高亮对应的目录节点"""
        root = self.project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            for j in range(project_item.childCount()):
                child = project_item.child(j)
                if child.text(0) == "DSL Cases":
                    self._find_and_highlight_directory_node(child, directory_name, parent_directory)
                    return

    def _find_and_highlight_directory_node(self, parent: QTreeWidgetItem, directory_name: str, parent_directory: str) -> bool:
        """递归查找并高亮目录节点"""
        target_path = str(PurePosixPath(parent_directory) / directory_name) if parent_directory else directory_name

        for i in range(parent.childCount()):
            item = parent.child(i)
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "directory":
                if item_data.get("path", "") == target_path:
                    self.project_tree.setCurrentItem(item)
                    self.project_tree.scrollToItem(item)
                    return True
                if self._find_and_highlight_directory_node(item, directory_name, parent_directory):
                    return True
        return False

    # ==================== 树节点事件 ====================

    def on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """项目树项点击事件"""
        modifiers = self.project_tree._last_click_modifiers
        if modifiers & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            return

        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        is_expandable = (
            item.childCount() > 0
            or (item_data and item_data.get("type") in ("directory", "automation_directory", "test_results_directory"))
        )

        if is_expandable:
            self._pending_expand_item = item
            self._expand_click_timer.start()
            return

        if item_data and item_data.get("type") == "file":
            file_path = item_data.get("path", "")
            if file_path.endswith('.dsl'):
                case_name = Path(file_path).stem
                path_parent = Path(file_path).parent
                directory = str(path_parent) if str(path_parent) != "." else ""
                self.open_case_text_editor(case_name, directory)
            return

        if item_data and item_data.get("type") == "automation_file":
            self.open_automation_file(item_data.get("path", ""), item_data.get("case_type", "py"))
            return

        if item_data and item_data.get("type") == "test_results_file":
            file_path = item_data.get("path", "")
            data_type = item_data.get("data_type", "trace")
            self.open_test_results_file(file_path, data_type)
            return

        tree_parent = item.parent()
        if tree_parent and tree_parent.text(0) == "DSL Cases":
            file_name = item.text(0)
            if file_name.endswith('.dsl'):
                self.open_case_text_editor(file_name[:-4])
        elif tree_parent and tree_parent.text(0) == "DBC文件":
            self.open_file_viewer(item.text(0), "CANoe/dbc_file")
        elif tree_parent and tree_parent.text(0) == "环境变量DBC文件":
            self.open_file_viewer(item.text(0), "CANoe/env_dbc")
        elif tree_parent and tree_parent.text(0) == "系统变量文件":
            self.open_file_viewer(item.text(0), "CANoe/system_variable")

    def _on_expand_click_timeout(self) -> None:
        """单击定时器到期，确认为单击而非双击，执行展开/折叠"""
        item = self._pending_expand_item
        self._pending_expand_item = None
        if item is None:
            return
        try:
            item.setExpanded(not item.isExpanded())
        except RuntimeError:
            pass

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """项目树项双击事件 - 打开文件编辑器"""
        self._expand_click_timer.stop()
        self._pending_expand_item = None

        tree_parent = item.parent()
        if not tree_parent:
            return

        parent_text = tree_parent.text(0)
        file_name = item.text(0)
        item_data = item.data(0, Qt.ItemDataRole.UserRole)

        if item_data and item_data.get("type") in ("directory", "automation_directory", "test_results_directory"):
            item.setExpanded(not item.isExpanded())
            return

        if item.childCount() > 0 and not (item_data and item_data.get("type") in ("file", "automation_file", "test_results_file")):
            item.setExpanded(not item.isExpanded())
            return

        if item_data and item_data.get("type") == "file":
            file_path = item_data.get("path", "")
            if file_path.endswith('.dsl'):
                case_name = Path(file_path).stem
                path_parent = Path(file_path).parent
                directory = str(path_parent) if str(path_parent) != "." else ""
                self.open_case_text_editor(case_name, directory)
            return

        if item_data and item_data.get("type") == "automation_file":
            self.open_automation_file(item_data.get("path", ""), item_data.get("case_type", "py"))
            return

        if item_data and item_data.get("type") == "test_results_file":
            file_path = item_data.get("path", "")
            data_type = item_data.get("data_type", "trace")
            self.open_test_results_file(file_path, data_type)
            return

        if parent_text == "DSL Cases":
            case_name = file_name[:-4] if file_name.endswith('.dsl') else file_name
            self.open_case_text_editor(case_name)
        elif parent_text == "DBC文件":
            self.open_file_viewer(file_name, "CANoe/dbc_file")
        elif parent_text == "环境变量DBC文件":
            self.open_file_viewer(file_name, "CANoe/env_dbc")
        elif parent_text == "系统变量文件":
            self.open_file_viewer(file_name, "CANoe/system_variable")
        elif parent_text == "面板文件":
            self.open_file_viewer(file_name, "CANoe/panel_files")

    def on_tree_context_menu(self, position) -> None:
        """项目树右键菜单"""
        item = self.project_tree.itemAt(position)
        if not item:
            return

        tree_parent = item.parent()
        item_text = item.text(0)
        item_data = item.data(0, Qt.ItemDataRole.UserRole)

        menu = QMenu(self)

        selected_items = self.project_tree.selectedItems()
        has_multiple_selection = len(selected_items) > 1

        # 多选批量操作
        if has_multiple_selection:
            items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in selected_items]
            all_dsl_items = all(
                d and d.get("type") in ("file", "directory") for d in items_data
            )
            all_automation_items = all(
                d and d.get("type") in ("automation_file", "automation_directory") for d in items_data
            )
            all_test_results_items = all(
                d and d.get("type") in ("test_results_file", "test_results_directory") for d in items_data
            )
            if all_dsl_items:
                menu.addAction("复制").triggered.connect(
                    lambda checked=False, data=items_data: self.copy_dsl_items(data)
                )
                menu.addAction("删除").triggered.connect(
                    lambda checked=False, data=items_data: self.delete_dsl_items(data)
                )
                menu.exec(self.project_tree.mapToGlobal(position))
                return
            if all_automation_items:
                menu.addAction("运行").triggered.connect(
                    lambda checked=False, data=items_data: self.run_selected_automation_items(data)
                )
                menu.addSeparator()
                menu.addAction("复制").triggered.connect(
                    lambda checked=False, data=items_data: self.copy_automation_items(data)
                )
                menu.addAction("删除").triggered.connect(
                    lambda checked=False, data=items_data: self.delete_automation_items(data)
                )
                menu.exec(self.project_tree.mapToGlobal(position))
                return
            if all_test_results_items:
                menu.addAction("复制").triggered.connect(
                    lambda checked=False, data=items_data: self.copy_test_results_items(data)
                )
                menu.addAction("删除").triggered.connect(
                    lambda checked=False, data=items_data: self.delete_test_results_items(data)
                )
                menu.exec(self.project_tree.mapToGlobal(position))
                return

        if item_text == "DSL Cases":
            menu.addAction("新建Case").triggered.connect(self.new_case)
            menu.addAction("添加目录").triggered.connect(
                lambda checked=False: self.add_dsl_directory("")
            )
            menu.addSeparator()
            menu.addAction("全部转换为 py/json").triggered.connect(
                lambda checked=False: self.convert_dsl_to_automation("", True)
            )

        elif item_data and item_data.get("type") == "directory":
            directory_path = item_data.get("path", "")
            menu.addAction("添加目录").triggered.connect(
                lambda checked=False, d=directory_path: self.add_dsl_directory(d)
            )
            menu.addAction("新建Case").triggered.connect(
                lambda checked=False, d=directory_path: self.new_case_in_directory(d)
            )
            menu.addSeparator()
            menu.addAction("批量转换为 py/json").triggered.connect(
                lambda checked=False, d=directory_path: self.convert_dsl_to_automation(d, False)
            )
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(
                lambda checked=False, d=directory_path: self.copy_dsl_directory(d)
            )
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda checked=False, d=directory_path: self.paste_dsl_item(d)
            )
            paste_action.setEnabled(self.clipboard is not None)
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(
                lambda checked=False, d=directory_path: self.rename_dsl_directory(d)
            )
            menu.addAction("删除目录").triggered.connect(
                lambda checked=False, d=directory_path: self.delete_dsl_directory(d)
            )

        elif item_data and item_data.get("type") == "file":
            file_path = item_data.get("path", "")
            if file_path.endswith('.dsl'):
                case_name = PurePosixPath(file_path).stem
                directory = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
                menu.addAction("编辑").triggered.connect(
                    lambda checked=False, cn=case_name, d=directory: self.open_case_modular_editor_with_directory(cn, d)
                )
                menu.addSeparator()
                menu.addAction("转换为 py/json").triggered.connect(
                    lambda checked=False, cn=case_name, d=directory: self.convert_single_dsl_to_automation(cn, d)
                )
                menu.addSeparator()
                menu.addAction("复制").triggered.connect(
                    lambda checked=False, cn=case_name, d=directory: self.copy_dsl_case(cn, d)
                )
                paste_action = menu.addAction("粘贴")
                paste_action.triggered.connect(
                    lambda checked=False, d=directory: self.paste_dsl_item(d)
                )
                paste_action.setEnabled(self.clipboard is not None)
                menu.addSeparator()
                menu.addAction("重命名").triggered.connect(
                    lambda checked=False, cn=case_name, d=directory: self.rename_dsl_case(cn, d)
                )
                menu.addAction("删除").triggered.connect(
                    lambda checked=False, cn=case_name, d=directory: self.delete_case_with_directory(cn, d)
                )

        elif tree_parent and tree_parent.text(0) == "DSL Cases":
            menu.addAction("编辑").triggered.connect(
                lambda checked=False, t=item_text: self.open_case_modular_editor(t)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, t=item_text: self.delete_case(t)
            )

        elif item_text == "DBC文件":
            menu.addAction("添加文件").triggered.connect(self.add_dbc_file)
        elif tree_parent and tree_parent.text(0) == "DBC文件":
            dbc_file_name = item.text(0)
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=dbc_file_name: self.delete_dbc_file(n)
            )

        elif item_text == "环境变量DBC文件":
            menu.addAction("添加文件").triggered.connect(self.add_env_dbc_file)
        elif tree_parent and tree_parent.text(0) == "环境变量DBC文件":
            env_dbc_file_name = item.text(0)
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=env_dbc_file_name: self.delete_env_dbc_file(n)
            )

        elif item_text == "系统变量文件":
            menu.addAction("添加文件").triggered.connect(self.add_system_variable_file)
        elif tree_parent and tree_parent.text(0) == "系统变量文件":
            sys_var_file_name = item.text(0)
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=sys_var_file_name: self.delete_system_variable_file(n)
            )

        elif item_text == "面板文件":
            # 面板文件目录的右键菜单
            pass
        elif tree_parent and tree_parent.text(0) == "面板文件":
            panel_file_name = item.text(0)
            menu.addAction("打开").triggered.connect(
                lambda checked=False, n=panel_file_name: self.open_file_viewer(n, "CANoe/panel_files")
            )
            menu.addAction("查看详情").triggered.connect(
                lambda checked=False, n=panel_file_name: self.show_panel_file_info(n)
            )
            menu.addSeparator()
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=panel_file_name: self.delete_panel_file(n)
            )

        elif item_text == "Scene":
            menu.addAction("添加场景映射表").triggered.connect(self.add_scene_mapping)
        elif tree_parent and tree_parent.text(0) == "Scene":
            mapping_name = item.text(0)
            menu.addAction("查看").triggered.connect(
                lambda checked=False, n=mapping_name: self.open_scene_mapping(n)
            )
            menu.addAction("刷新").triggered.connect(
                lambda checked=False, n=mapping_name: self.refresh_scene_mapping(n)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=mapping_name: self.delete_scene_mapping(n)
            )

        elif item_text == "Test Requirements":
            menu.addAction("添加测试需求文档").triggered.connect(self.add_test_requirement)
        elif tree_parent and tree_parent.text(0) == "Test Requirements":
            doc_name = item.text(0)
            menu.addAction("查看").triggered.connect(
                lambda checked=False, n=doc_name: self.open_test_requirement(n)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, n=doc_name: self.delete_test_requirement(n)
            )

        elif item_text == "Automation Cases":
            pass

        elif item_text == "py_cases":
            menu.addAction("运行").triggered.connect(
                lambda checked=False: self.run_selected_automation_items([
                    {"type": "automation_directory", "path": "", "case_type": "py"}
                ])
            )
            menu.addSeparator()
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_automation_directory("py_cases")
            )

        elif item_text == "json_cases":
            menu.addAction("运行").triggered.connect(
                lambda checked=False: self.run_selected_automation_items([
                    {"type": "automation_directory", "path": "", "case_type": "json"}
                ])
            )
            menu.addSeparator()
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_automation_directory("json_cases")
            )

        elif item_data and item_data.get("type") == "automation_directory":
            dir_path = item_data.get("path", "")
            case_type = item_data.get("case_type", "py")
            parent_key = f"{case_type}_cases/{dir_path}" if dir_path else f"{case_type}_cases"
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False, p=parent_key: self.add_automation_directory(p)
            )
            menu.addAction("运行").triggered.connect(
                lambda checked=False, d=dir_path, ct=case_type: self.run_selected_automation_items([
                    {"type": "automation_directory", "path": d, "case_type": ct}
                ])
            )
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(
                lambda checked=False, d=dir_path, ct=case_type: self.copy_automation_directory(d, ct)
            )
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda checked=False, d=dir_path, ct=case_type: self.paste_automation_item(d, ct)
            )
            paste_action.setEnabled(
                self.clipboard is not None and self.clipboard.get("type") in ("automation_file", "automation_directory", "automation_items")
            )
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(
                lambda checked=False, d=dir_path, ct=case_type: self.rename_automation_directory(d, ct)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, d=dir_path, ct=case_type: self.delete_automation_directory(d, ct)
            )

        elif item_data and item_data.get("type") == "automation_file":
            file_path = item_data.get("path", "")
            case_type = item_data.get("case_type", "py")
            directory = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
            menu.addAction("打开").triggered.connect(
                lambda checked=False, p=file_path, ct=case_type: self.open_automation_file(p, ct)
            )
            menu.addAction("运行").triggered.connect(
                lambda checked=False, p=file_path, ct=case_type: self.run_selected_automation_items([
                    {"type": "automation_file", "path": p, "case_type": ct}
                ])
            )
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(
                lambda checked=False, p=file_path, ct=case_type: self.copy_automation_file(p, ct)
            )
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda checked=False, d=directory, ct=case_type: self.paste_automation_item(d, ct)
            )
            paste_action.setEnabled(
                self.clipboard is not None and self.clipboard.get("type") in ("automation_file", "automation_directory", "automation_items")
            )
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(
                lambda checked=False, p=file_path, ct=case_type: self.rename_automation_file(p, ct)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, p=file_path, ct=case_type: self.delete_automation_file(p, ct)
            )

        # Test Results 相关菜单
        elif item_text == "Test Results":
            pass  # Test Results 主节点无菜单

        elif item_text == "trace data":
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_test_results_directory("trace_data")
            )

        elif item_text == "record data":
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_test_results_directory("record_data")
            )

        elif item_text == "log data":
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_test_results_directory("log_data")
            )

        elif item_text == "report data":
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False: self.add_test_results_directory("report_data")
            )

        elif item_data and item_data.get("type") == "test_results_directory":
            dir_path = item_data.get("path", "")
            data_type = item_data.get("data_type", "trace")
            parent_key = f"{data_type}_data/{dir_path}" if dir_path else f"{data_type}_data"
            menu.addAction("新增子目录").triggered.connect(
                lambda checked=False, p=parent_key: self.add_test_results_directory(p)
            )
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(
                lambda checked=False, d=dir_path, dt=data_type: self.copy_test_results_directory(d, dt)
            )
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda checked=False, d=dir_path, dt=data_type: self.paste_test_results_item(d, dt)
            )
            paste_action.setEnabled(
                self.clipboard is not None and self.clipboard.get("type") in ("test_results_file", "test_results_directory", "test_results_items")
            )
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(
                lambda checked=False, d=dir_path, dt=data_type: self.rename_test_results_directory(d, dt)
            )
            menu.addAction("删除").triggered.connect(
                lambda checked=False, d=dir_path, dt=data_type: self.delete_test_results_directory(d, dt)
            )

        elif item_data and item_data.get("type") == "test_results_file":
            file_path = item_data.get("path", "")
            data_type = item_data.get("data_type", "trace")
            directory = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
            file_name = Path(file_path).name

            menu.addAction("打开").triggered.connect(
                lambda checked=False, p=file_path, dt=data_type: self.open_test_results_file(p, dt)
            )
            # Add "Open in Browser" for HTML files
            if data_type == "report" and file_name.endswith(".html"):
                full_path = self.project_manager.current_project_path / "Test Results" / "report data" / file_path
                menu.addAction("用 Edge 打开").triggered.connect(
                    lambda checked=False, fp=str(full_path): self.open_html_in_browser(fp)
                )
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(
                lambda checked=False, p=file_path, dt=data_type: self.copy_test_results_file(p, dt)
            )
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(
                lambda checked=False, d=directory, dt=data_type: self.paste_test_results_item(d, dt)
            )
            paste_action.setEnabled(
                self.clipboard is not None and self.clipboard.get("type") in ("test_results_file", "test_results_directory", "test_results_items")
            )
            menu.addSeparator()
            menu.addAction("删除").triggered.connect(
                lambda checked=False, p=file_path, dt=data_type: self.delete_test_results_file(p, dt)
            )
            # Only show "回放" for trace/record files
            if data_type in ("trace", "record"):
                menu.addAction("回放").triggered.connect(
                    lambda checked=False, p=file_path, dt=data_type: self.replay_file(p, dt)
                )

        menu.exec(self.project_tree.mapToGlobal(position))
    
    def _build_automation_run_targets(self, items_data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """把树节点数据转换为运行目标；目录优先，自动去重"""
        if isinstance(items_data, bool) or items_data is None:
            # 防御式处理：避免 QAction.triggered(bool) 覆盖默认参数
            items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in self.project_tree.selectedItems()]

        if not isinstance(items_data, list):
            return []

        def _normalize_rel_path(raw_path: Any) -> str:
            if isinstance(raw_path, bool) or raw_path is None:
                return ""
            if isinstance(raw_path, os.PathLike):
                raw_path = os.fspath(raw_path)
            if not isinstance(raw_path, str):
                return ""
            path = str(PurePosixPath(raw_path)) if raw_path else ""
            return "" if path == "." else path

        def _infer_path_from_tree(node_type: str, case_type: str) -> str:
            """当入参 path 被信号 bool 覆盖时，从当前树选择恢复 path"""
            current_item = self.project_tree.currentItem()
            if current_item:
                current_data = current_item.data(0, Qt.ItemDataRole.UserRole)
                if (
                    isinstance(current_data, dict)
                    and current_data.get("type") == node_type
                    and current_data.get("case_type", "py") == case_type
                ):
                    p = _normalize_rel_path(current_data.get("path", ""))
                    if p or node_type == "automation_directory":
                        return p

            candidates: List[str] = []
            for si in self.project_tree.selectedItems():
                data = si.data(0, Qt.ItemDataRole.UserRole)
                if (
                    isinstance(data, dict)
                    and data.get("type") == node_type
                    and data.get("case_type", "py") == case_type
                ):
                    p = _normalize_rel_path(data.get("path", ""))
                    if p or node_type == "automation_directory":
                        candidates.append(p)

            if len(candidates) == 1:
                return candidates[0]
            return ""

        directories: List[Dict[str, str]] = []
        files: List[Dict[str, str]] = []
        seen = set()

        for item_data in items_data:
            if not isinstance(item_data, dict):
                continue

            node_type = item_data.get("type")
            if node_type not in ("automation_file", "automation_directory"):
                continue

            case_type = item_data.get("case_type", "py")
            path = _normalize_rel_path(item_data.get("path", ""))

            # 单文件“运行”菜单中，QAction.triggered(bool) 可能把 path 覆盖成 False
            if not path and node_type in ("automation_file", "automation_directory"):
                inferred = _infer_path_from_tree(node_type, case_type)
                if inferred or node_type == "automation_directory":
                    path = inferred

            # 文件目标必须有有效路径
            if node_type == "automation_file" and not path:
                continue

            kind = "directory" if node_type == "automation_directory" else "file"
            key = (kind, case_type, path)
            if key in seen:
                continue
            seen.add(key)

            target = {"kind": kind, "case_type": case_type, "path": path}
            if kind == "directory":
                directories.append(target)
            else:
                files.append(target)

        # 若目录已选中，去掉目录内重复文件
        filtered_files: List[Dict[str, str]] = []
        for file_target in files:
            file_case_type = file_target["case_type"]
            file_path = file_target["path"]

            covered = False
            for dir_target in directories:
                if file_case_type != dir_target["case_type"]:
                    continue
                dir_path = dir_target["path"]

                if not dir_path:
                    covered = True
                    break
                if file_path == dir_path or file_path.startswith(dir_path + "/"):
                    covered = True
                    break

            if not covered:
                filtered_files.append(file_target)

        return directories + filtered_files

    def _resolve_automation_case_paths(self, run_targets: List[Dict[str, str]]) -> Tuple[str, List[str]]:
        """将运行目标解析为具体 case 文件的完整路径"""
        if not run_targets:
            return "", []

        case_types = {t.get("case_type", "py") for t in run_targets}
        if len(case_types) != 1:
            return "", []

        case_type = next(iter(case_types))
        suffix = ".py" if case_type == "py" else ".json"
        base_dir = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"

        case_paths: List[str] = []
        seen = set()

        def add_case_path(full_path: str) -> None:
            fp = full_path.replace("\\", "/")
            if fp and fp not in seen:
                seen.add(fp)
                case_paths.append(fp)

        for target in run_targets:
            if target.get("case_type") != case_type:
                continue

            kind = target.get("kind")
            rel_path = target.get("path", "")

            if kind == "file":
                if not rel_path.endswith(suffix):
                    continue
                abs_file = base_dir / rel_path
                if abs_file.exists() and abs_file.is_file():
                    add_case_path(str(abs_file))

            elif kind == "directory":
                abs_dir = base_dir / rel_path if rel_path else base_dir
                if not abs_dir.exists() or not abs_dir.is_dir():
                    continue

                for fp in sorted(abs_dir.rglob(f"*{suffix}")):
                    add_case_path(str(fp))

        return case_type, case_paths

    def run_selected_automation_items(self, items_data: List[Dict[str, Any]]) -> None:
        """运行选中的 automation 文件/目录（支持多选；仅允许同一 case_type）"""
        run_targets = self._build_automation_run_targets(items_data)
        if not run_targets:
            QMessageBox.information(self, "提示", "未选择可运行的 Automation 项目")
            return

        case_types = {t.get("case_type", "py") for t in run_targets}
        if len(case_types) != 1:
            QMessageBox.warning(
                self,
                "提示",
                "只能选择同一类型的 case 运行，请只选择 py_cases 或只选择 json_cases 下的case"
            )
            return

        case_type, case_paths = self._resolve_automation_case_paths(run_targets)
        if not case_type or not case_paths:
            QMessageBox.warning(self, "提示", "未解析到可运行的 case 路径")
            return

        # 弹出配置对话框
        from .dialogs import RunAutomationDialog
        dialog = RunAutomationDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        config = dialog.get_config()
        output_dir = config.get("output_dir", "")
        domain_version = config.get("domain_version", "")

        self.run_automation(case_type, case_paths, output_dir, domain_version)
        self.update_status(f"已提交运行请求：{case_type}_cases，共 {len(case_paths)} 个 case")

    def run_automation_pycases(self, case_paths: List[str], project_json_path: str,
                               project_path, output_dir: str, domain_version: str) -> None:
        """Run Python type Automation Cases"""
        for case_path in case_paths:
            # TODO: Implement actual run logic
            pass

    def run_automation_jsoncases(self, case_paths: List[str], project_json_path: str,
                                  project_path: str, output_dir: str, domain_version: str,
                                  ) -> None:
        """Run JSON type Automation Cases with output dialog and logging"""
        from .dialogs import OutputDialog

        # Create output dialog
        output_dialog = OutputDialog(self)
        output_dialog.setWindowTitle(f"Running Automation Cases - {output_dir}/{domain_version}")

        # Setup log file
        log_dir = os.path.join(project_path, "Test Results", "log data", output_dir, domain_version)
        log_file = output_dialog.setup_log_file(log_dir, "run")
        print(f"Log file: {log_file}")

        # Show dialog
        output_dialog.show()

        # Redirect output
        output_dialog.redirect_output()

        # Mark task as running
        output_dialog.set_task_running(True)

        # Create worker thread
        class RunWorker(QThread):
            finished = pyqtSignal()

            def __init__(self, case_paths, project_json_path, project_path, output_dir, domain_version, output_dialog):
                super().__init__()
                self.case_paths = case_paths
                self.project_json_path = project_json_path
                self.project_path = project_path
                self.output_dir = output_dir
                self.domain_version = domain_version
                self.output_dialog = output_dialog

            def run(self):
                try:
                    from .run_case import Main
                    app = Main(
                        case_paths=self.case_paths,
                        project_json_path=self.project_json_path,
                        project_path=self.project_path,
                        delay_time_after_success_or_failure_for_logging=5000,
                        sampling_rate=10,
                        max_workers=8,
                        out_path=self.output_dir,
                        adc_version=self.domain_version,
                        stop_callback=self._check_stop,
                    )
                    app.auto_execute()
                finally:
                    self.finished.emit()

            def _check_stop(self) -> bool:
                """Check if stop is requested"""
                return self.output_dialog.is_stop_requested()

        # Create and start worker
        self._run_worker = RunWorker(case_paths, project_json_path, project_path, output_dir, domain_version, output_dialog)
        self._output_dialog = output_dialog

        def on_finished():
            print("\n=== Automation run completed ===")
            # Restore stdout/stderr first
            try:
                output_dialog.restore_output()
                output_dialog.close_log_file()
            except Exception as e:
                print(f"Warning: restore/close log error: {e}")

            # Update status and sync results
            try:
                self.update_status(f"Automation run completed: {output_dir}/{domain_version}")
                self.project_manager.sync_test_results()
                self.update_project_tree()
            except Exception as e:
                print(f"Warning: status update error: {e}")

            # Clean up worker thread first, before closing dialog
            if self._run_worker is not None:
                self._run_worker.wait()  # Wait for thread to fully exit
                self._run_worker.deleteLater()  # Schedule for deletion
                self._run_worker = None
            self._output_dialog = None

            # Mark task as completed and close dialog
            output_dialog.set_task_running(False)
            print("=== Cleanup completed ===")

        self._run_worker.finished.connect(on_finished)
        self._run_worker.start()

    def run_automation(self, case_type: str, case_paths: List[str],
                       output_dir: str, domain_version: str) -> None:
        project_path = str(self.project_manager.current_project_path)
        project_json_path = str(self.project_manager.current_project_path / "project.json")
        # print(f"case_paths: {case_paths}")
        # print(f"project_json_path: {project_json_path}")
        # print(f"project_path: {project_path}")
        # print(f"output_dir: {output_dir}, domain_version: {domain_version}")
        """运行入口：按 case_type 分发到对应运行函数"""
        if case_type == "py":
            runner = getattr(self, "run_automation_pycases", None)
            if callable(runner):
                runner(case_paths, project_json_path, project_path, output_dir, domain_version)
            else:
                QMessageBox.warning(self, "提示", "未找到运行函数 run_automation_pycases")
            return

        if case_type == "json":
            # 按你给的函数名使用 run_autonmation_jsoncases（保留原拼写）
            runner = getattr(self, "run_automation_jsoncases", None)

            if callable(runner):
                runner(case_paths, project_json_path, project_path, output_dir, domain_version)
            else:
                QMessageBox.warning(self, "提示", "未找到运行函数 run_automation_jsoncases")
            return

        QMessageBox.warning(self, "提示", f"不支持的 case 类型: {case_type}")
    
    # ==================== 文件添加/删除 (CANoe) ====================

    def add_dbc_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        # 使用 getOpenFileNames 支持多选
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择DBC文件", "", "DBC文件 (*.dbc);;所有文件 (*.*)")
        if not file_paths:
            return

        success_count = 0
        failed_files = []
        for file_path in file_paths:
            if self.project_manager.add_dbc_file(file_path):
                dbc_name = Path(file_path).name
                project_dbc_path = self.project_manager.get_full_path(f"CANoe/dbc_file/{dbc_name}")
                if project_dbc_path:
                    self.dbc_parser.load_dbc_file(str(project_dbc_path), "normal")
                success_count += 1
            else:
                failed_files.append(Path(file_path).name)

        self.update_project_tree()
        self.update_all_editor_completions()

        if success_count > 0:
            if len(file_paths) == 1:
                self.update_status(f"DBC文件 '{Path(file_paths[0]).name}' 添加成功")
            else:
                self.update_status(f"成功添加 {success_count} 个DBC文件")
        if failed_files:
            QMessageBox.warning(self, "警告", f"以下文件添加失败:\n{', '.join(failed_files)}")

    def add_env_dbc_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        # 使用 getOpenFileNames 支持多选
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择环境变量DBC文件", "", "DBC文件 (*.dbc);;所有文件 (*.*)")
        if not file_paths:
            return

        success_count = 0
        failed_files = []
        for file_path in file_paths:
            if self.project_manager.add_env_dbc_file(file_path):
                dbc_name = Path(file_path).name
                project_dbc_path = self.project_manager.get_full_path(f"CANoe/env_dbc/{dbc_name}")
                if project_dbc_path:
                    self.dbc_parser.load_dbc_file(str(project_dbc_path), "env")
                success_count += 1
            else:
                failed_files.append(Path(file_path).name)

        self.update_project_tree()
        self.update_all_editor_completions()

        if success_count > 0:
            if len(file_paths) == 1:
                self.update_status(f"环境变量DBC文件 '{Path(file_paths[0]).name}' 添加成功")
            else:
                self.update_status(f"成功添加 {success_count} 个环境变量DBC文件")
        if failed_files:
            QMessageBox.warning(self, "警告", f"以下文件添加失败:\n{', '.join(failed_files)}")

    def add_system_variable_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        # 使用 getOpenFileNames 支持多选
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择系统变量文件", "", "系统变量文件 (*.vsysvar *.xml);;所有文件 (*.*)")
        if not file_paths:
            return

        success_count = 0
        failed_files = []
        for file_path in file_paths:
            if self.project_manager.add_system_variable_file(file_path):
                file_name = Path(file_path).name
                project_sysvar_path = self.project_manager.get_full_path(f"CANoe/system_variable/{file_name}")
                if project_sysvar_path:
                    self.dbc_parser.load_system_variables(str(project_sysvar_path))
                success_count += 1
            else:
                failed_files.append(Path(file_path).name)

        self.update_project_tree()
        self.update_all_editor_completions()

        if success_count > 0:
            if len(file_paths) == 1:
                self.update_status(f"系统变量文件 '{Path(file_paths[0]).name}' 添加成功")
            else:
                self.update_status(f"成功添加 {success_count} 个系统变量文件")
        if failed_files:
            QMessageBox.warning(self, "警告", f"以下文件添加失败:\n{', '.join(failed_files)}")

    def config_can_mapping(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        dialog = DBCMappingDialog(self.project_manager.get_dbc_files(),
                                  self.project_manager.get_can_channel_mapping(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mapping = dialog.get_mapping()
            if self.project_manager.set_can_channel_mapping(mapping):
                # 将相对路径转换为绝对路径给 dbc_parser
                absolute_mapping = {}
                for rel_path, info in mapping.items():
                    abs_path = self.project_manager.get_full_path(rel_path)
                    if abs_path:
                        absolute_mapping[str(abs_path)] = info
                self.dbc_parser.set_can_channel_mapping(absolute_mapping)
                self.update_all_editor_completions()
                self.update_status("CAN通道映射配置成功")
            else:
                QMessageBox.critical(self, "错误", "保存CAN通道映射失败")

    def config_canoe_project(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        current_path = self.project_manager.get_canoe_project_path()
        dialog = CANoeProjectDialog(current_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project_path = dialog.get_project_path()
            if self.project_manager.set_canoe_project_path(project_path):
                self.update_project_tree()
                self.update_status("CANoe工程文件配置成功")
            else:
                QMessageBox.critical(self, "错误", "保存CANoe工程文件失败")

    def manage_simulink_files(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        current_files = self.project_manager.get_simulink_files()
        current_file_names = {f["name"] for f in current_files}
        dialog = SimulinkFileDialog(current_files, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_files = dialog.get_files()
            new_file_names = {f["name"] for f in new_files}

            # 删除被移除的文件
            removed_file_names = current_file_names - new_file_names
            for file_name in removed_file_names:
                self.project_manager.remove_simulink_file(file_name)

            # 添加新文件
            added_file_names = new_file_names - current_file_names
            for file_info in new_files:
                if file_info["name"] in added_file_names:
                    self.project_manager.add_simulink_file(file_info["path"], file_info["type"], copy_to_project=False)

            self.update_project_tree()
            self.update_status("Simulink工程文件配置成功")

    def delete_dbc_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除DBC文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 获取文件路径用于撤销
            file_dir = self.project_manager.current_project_path / "CANoe" / "dbc_file"
            file_path = file_dir / file_name

            # 读取文件内容用于撤销
            file_content = None
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    file_content = f.read()

            success, abs_path = self.project_manager.remove_dbc_file(file_name)
            if success:
                # 记录撤销信息
                if file_content is not None:
                    undo_info = {
                        "operation": "delete_dbc_file",
                        "file_name": file_name,
                        "file_content": file_content,
                        "file_path": str(file_path)
                    }
                    self._push_undo_info(undo_info)

                if abs_path:
                    self.dbc_parser.unload_dbc_file(abs_path)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"DBC文件 '{file_name}' 已删除")
            else:
                # 删除失败时移除撤销记录
                if self._undo_stack and self._undo_stack[-1].get("operation") == "delete_dbc_file":
                    self._undo_stack.pop()
                QMessageBox.critical(self, "错误", f"删除DBC文件 '{file_name}' 失败")

    def delete_env_dbc_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除环境变量DBC文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 获取文件路径用于撤销
            file_dir = self.project_manager.current_project_path / "CANoe" / "env_dbc"
            file_path = file_dir / file_name

            # 读取文件内容用于撤销
            file_content = None
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    file_content = f.read()

            success, abs_path = self.project_manager.remove_env_dbc_file(file_name)
            if success:
                # 记录撤销信息
                if file_content is not None:
                    undo_info = {
                        "operation": "delete_env_dbc_file",
                        "file_name": file_name,
                        "file_content": file_content,
                        "file_path": str(file_path)
                    }
                    self._push_undo_info(undo_info)

                if abs_path:
                    self.dbc_parser.unload_dbc_file(abs_path)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"环境变量DBC文件 '{file_name}' 已删除")
            else:
                # 删除失败时移除撤销记录
                if self._undo_stack and self._undo_stack[-1].get("operation") == "delete_env_dbc_file":
                    self._undo_stack.pop()
                QMessageBox.critical(self, "错误", f"删除环境变量DBC文件 '{file_name}' 失败")

    def delete_system_variable_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除系统变量文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 获取文件路径用于撤销
            file_dir = self.project_manager.current_project_path / "CANoe" / "system_variable"
            file_path = file_dir / file_name

            # 读取文件内容用于撤销
            file_content = None
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    file_content = f.read()

            success, abs_path = self.project_manager.remove_system_variable_file(file_name)
            if success:
                # 记录撤销信息
                if file_content is not None:
                    undo_info = {
                        "operation": "delete_system_variable_file",
                        "file_name": file_name,
                        "file_content": file_content,
                        "file_path": str(file_path)
                    }
                    self._push_undo_info(undo_info)

                if abs_path:
                    self.dbc_parser.remove_system_variables(abs_path)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"系统变量文件 '{file_name}' 已删除")
            else:
                # 删除失败时移除撤销记录
                if self._undo_stack and self._undo_stack[-1].get("operation") == "delete_system_variable_file":
                    self._undo_stack.pop()
                QMessageBox.critical(self, "错误", f"删除系统变量文件 '{file_name}' 失败")

    def show_panel_file_info(self, file_name: str) -> None:
        """显示面板文件详情"""
        if not self.project_manager.is_project_open():
            return

        # 从配置中获取面板信息
        panel_files = self.project_manager.get_panel_files()
        panel_info = None
        for info in panel_files:
            if info.get("name") == file_name:
                panel_info = info
                break

        if not panel_info:
            # 如果配置中没有，从文件名解析基本信息
            panel_info = {
                "name": file_name,
                "namespace": "",
                "message_name": "",
                "created_time": "",
                "path": f"CANoe/panel_files/{file_name}"
            }
            # 从文件名解析
            parts = file_name.replace("_panel.xvp", "").split("_")
            if len(parts) >= 1:
                panel_info["namespace"] = parts[0]
            if len(parts) >= 2:
                panel_info["message_name"] = parts[-1]

        # 显示详情对话框
        dialog = PanelFileInfoDialog(panel_info, self)
        dialog.exec()

    def delete_panel_file(self, file_name: str) -> None:
        """删除面板文件"""
        if not self.project_manager.is_project_open():
            return

        reply = QMessageBox.question(self, "确认删除", f"确定要删除面板文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 获取文件路径
        panel_dir = self.project_manager.get_panel_dir()
        if not panel_dir:
            return
        file_path = panel_dir / file_name

        # 读取文件内容用于撤销
        file_content = None
        panel_info = None
        if file_path.exists():
            with open(file_path, 'rb') as f:
                file_content = f.read()

        # 获取面板信息用于撤销
        panel_files = self.project_manager.get_panel_files()
        for info in panel_files:
            if info.get("name") == file_name:
                panel_info = info.copy()
                break

        # 删除文件
        success = False
        try:
            if file_path.exists():
                file_path.unlink()
            success = True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除文件失败: {str(e)}")
            return

        if success:
            # 从配置中移除
            self.project_manager.remove_panel_file(file_name)

            # 记录撤销信息
            if file_content is not None:
                undo_info = {
                    "operation": "delete_panel_file",
                    "file_name": file_name,
                    "file_content": file_content,
                    "file_path": str(file_path),
                    "panel_info": panel_info
                }
                self._push_undo_info(undo_info)

            self.update_project_tree()
            self.update_status(f"面板文件 '{file_name}' 已删除（可按 Ctrl+Z 撤销）")

    # ==================== DSL Case 操作 ====================

    def new_case(self) -> None:
        """新建Case"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return

        # 根据当前树节点推断目标目录
        directory = ""
        current_item = self.project_tree.currentItem()
        if current_item:
            item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "directory":
                directory = item_data.get("path", "")
            elif item_data and item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path:
                    p = Path(file_path).parent
                    directory = str(p) if str(p) != "." else ""

        file_name, ok = QInputDialog.getText(self, "新建Case", "请输入文件名（不需要.dsl后缀）:")
        if not ok or not file_name:
            return
        if file_name.endswith('.dsl'):
            file_name = file_name[:-4]

        dsl_template = f"CASE: {file_name}\n"
        if not self.project_manager.add_dsl_case(file_name, dsl_template, directory):
            QMessageBox.critical(self, "错误", f"创建文件 '{file_name}.dsl' 失败")
            return

        self.update_project_tree(restore_selection=False)
        self.open_case_modular_editor_with_directory(file_name, directory)
        self.update_status(f"新建Case '{file_name}.dsl'" + (f"（目录: {directory}）" if directory else ""))

    def new_case_in_directory(self, directory: str) -> None:
        """在指定目录中新建Case"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return

        file_name, ok = QInputDialog.getText(self, "新建Case", "请输入文件名（不需要.dsl后缀）:")
        if not ok or not file_name:
            return
        if file_name.endswith('.dsl'):
            file_name = file_name[:-4]

        dsl_template = f"CASE: {file_name}\n"
        if not self.project_manager.add_dsl_case(file_name, dsl_template, directory):
            QMessageBox.critical(self, "错误", f"创建文件 '{file_name}.dsl' 失败")
            return

        self.update_project_tree(restore_selection=False)
        self.open_case_modular_editor_with_directory(file_name, directory)
        self.update_status(f"在目录 '{directory}' 中新建Case '{file_name}.dsl'")

    def add_dsl_directory(self, parent_directory: str) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        dir_name, ok = QInputDialog.getText(self, "添加目录", "请输入目录名称:")
        if ok and dir_name:
            if self.project_manager.create_dsl_directory(dir_name, parent_directory):
                self.update_project_tree()
                self.update_status(f"目录 '{dir_name}' 创建成功")
            else:
                QMessageBox.critical(self, "错误", f"创建目录 '{dir_name}' 失败")

    def delete_case(self, file_name: str) -> None:
        """删除Case（兼容旧调用方式）"""
        case_name = file_name[:-4] if file_name.endswith('.dsl') else file_name
        self.delete_case_with_directory(case_name, "")

    def delete_case_with_directory(self, case_name: str, directory: str) -> None:
        """删除指定目录中的Case"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除Case '{case_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        file_path = self.project_manager.current_project_path / "dsl_case"
        if directory:
            file_path = file_path / directory
        file_path = file_path / f"{case_name}.dsl"

        content = ""
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        case_info = None
        for c in self.project_manager.project_config.get("dsl_cases", []):
            if c["name"] == case_name and c.get("directory", "") == directory:
                case_info = c
                break

        undo_info = {
            "operation": "delete_dsl_file", "file_path": str(file_path),
            "content": content, "case_name": case_name, "directory": directory,
            "created_time": case_info.get("created_time", "") if case_info else ""
        }
        self._push_undo_info(undo_info)

        if self.project_manager.delete_dsl_case(case_name, directory):
            file_key = f"{directory}/{case_name}" if directory else case_name
            self.close_case_tab(file_key)
            self.update_project_tree()
            self.update_status(f"Case '{case_name}' 已删除（可按 Ctrl+Z 撤销）")
        else:
            if self._undo_stack and self._undo_stack[-1] is undo_info:
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除Case '{case_name}' 失败")

    def delete_dsl_directory(self, directory: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除目录 '{directory}' 及其所有内容吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        dir_path = self.project_manager.current_project_path / "dsl_case" / directory
        files_info = []
        if dir_path.exists():
            for dsl_file in dir_path.rglob("*.dsl"):
                rel_path = dsl_file.relative_to(dir_path)
                file_directory = str(rel_path.parent) if rel_path.parent != Path(".") else ""
                if directory:
                    file_directory = f"{directory}/{file_directory}" if file_directory else directory
                with open(dsl_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                c_name = dsl_file.stem
                c_info = next((c for c in self.project_manager.project_config.get("dsl_cases", [])
                            if c["name"] == c_name and c.get("directory", "") == file_directory), None)
                files_info.append({
                    "file_path": str(dsl_file), "content": content,
                    "case_name": c_name, "directory": file_directory,
                    "created_time": c_info.get("created_time", "") if c_info else ""
                })

        undo_info = {"operation": "delete_dsl_directory", "directory": directory, "files_info": files_info}
        self._push_undo_info(undo_info)

        self.file_watcher.blockSignals(True)
        try:
            self._remove_watch_paths_under(dir_path)
            QApplication.processEvents()
            time.sleep(0.03)
            QApplication.processEvents()
            success = self.project_manager.delete_dsl_directory(directory)
        finally:
            self.file_watcher.blockSignals(False)

        if success:
            self.update_project_tree()
            self._sync_file_watcher()
            self.update_status(f"目录 '{directory}' 已删除（可按 Ctrl+Z 撤销）")
        else:
            if self._undo_stack and self._undo_stack[-1] is undo_info:
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除目录 '{directory}' 失败")

    def rename_dsl_case(self, case_name: str, directory: str) -> None:
        new_name, ok = QInputDialog.getText(self, "重命名Case", "请输入新的文件名（不需要.dsl后缀）:", text=case_name)
        if not ok or not new_name:
            return
        if new_name.endswith('.dsl'):
            new_name = new_name[:-4]
        if new_name == case_name:
            return
        if self.project_manager.rename_dsl_case(case_name, new_name, directory):
            old_file_key = f"{directory}/{case_name}" if directory else case_name
            self.close_case_tab(old_file_key)
            self.update_project_tree()
            self.update_status(f"Case '{case_name}.dsl' 已重命名为 '{new_name}.dsl'")
        else:
            QMessageBox.critical(self, "错误", "重命名Case失败")

    def rename_dsl_directory(self, directory: str) -> None:
        current_name = directory.split("/")[-1] if "/" in directory else directory
        new_name, ok = QInputDialog.getText(self, "重命名目录", "请输入新的目录名:", text=current_name)
        if not ok or not new_name or new_name == current_name:
            return
        if self.project_manager.rename_dsl_directory(directory, new_name):
            self.close_directory_tabs(directory)
            self.update_project_tree()
            self.update_status(f"目录 '{directory}' 已重命名为 '{new_name}'")
        else:
            QMessageBox.critical(self, "错误", "重命名目录失败")

    def delete_dsl_items(self, items_data: List[Dict[str, Any]]) -> None:
        """批量删除 DSL 文件和目录（覆盖 dsl_case 子目录）"""
        if not items_data:
            return
        file_count = sum(1 for d in items_data if d and d.get("type") == "file")
        dir_count = sum(1 for d in items_data if d and d.get("type") == "directory")

        message = "确定要删除以下项目吗？\n\n"
        if file_count > 0:
            message += f"文件: {file_count} 个\n"
        if dir_count > 0:
            message += f"目录: {dir_count} 个\n"

        reply = QMessageBox.question(self, "确认删除", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        batch_entries: List[Dict[str, Any]] = []
        delete_tasks: List[Dict[str, Any]] = []

        for item_data in items_data:
            if not item_data:
                continue
            if item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path.endswith('.dsl'):
                    cn = Path(file_path).stem
                    d = str(Path(file_path).parent) if Path(file_path).parent != Path(".") else ""
                    abs_path = self.project_manager.current_project_path / "dsl_case"
                    if d:
                        abs_path = abs_path / d
                    abs_path = abs_path / f"{cn}.dsl"
                    content = ""
                    if abs_path.exists():
                        with open(abs_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    c_info = next(
                        (c for c in self.project_manager.project_config.get("dsl_cases", [])
                        if c["name"] == cn and c.get("directory", "") == d), None
                    )
                    batch_entries.append({
                        "kind": "file", "file_path": str(abs_path), "content": content,
                        "case_name": cn, "directory": d,
                        "created_time": c_info.get("created_time", "") if c_info else ""
                    })
                    delete_tasks.append({"type": "file", "case_name": cn, "directory": d, "abs_path": abs_path})
            elif item_data and item_data.get("type") == "directory":
                d = item_data.get("path", "")
                dir_path = self.project_manager.current_project_path / "dsl_case" / d
                files_info = []
                if dir_path.exists():
                    for dsl_file in dir_path.rglob("*.dsl"):
                        rel_path = dsl_file.relative_to(dir_path)
                        file_directory = str(rel_path.parent) if rel_path.parent != Path(".") else ""
                        if d:
                            file_directory = f"{d}/{file_directory}" if file_directory else d
                        with open(dsl_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        c_name = dsl_file.stem
                        c_info = next(
                            (c for c in self.project_manager.project_config.get("dsl_cases", [])
                            if c["name"] == c_name and c.get("directory", "") == file_directory), None
                        )
                        files_info.append({
                            "file_path": str(dsl_file), "content": content,
                            "case_name": c_name, "directory": file_directory,
                            "created_time": c_info.get("created_time", "") if c_info else ""
                        })
                batch_entries.append({"kind": "directory", "directory": d, "files_info": files_info})
                delete_tasks.append({"type": "directory", "directory": d, "abs_dir": dir_path})

        # 目录优先且深层优先，避免重复删除
        dir_tasks = [t for t in delete_tasks if t["type"] == "directory"]
        dir_tasks.sort(key=lambda t: len(PurePosixPath(t["directory"]).parts), reverse=True)
        file_tasks = [t for t in delete_tasks if t["type"] == "file"]

        selected_dirs = [t["directory"] for t in dir_tasks]
        success_count = 0

        self.file_watcher.blockSignals(True)
        try:
            for task in dir_tasks:
                self._remove_watch_paths_under(task["abs_dir"])

            for task in file_tasks:
                file_dir = task["directory"]
                covered = any(file_dir == d or file_dir.startswith(d + "/") for d in selected_dirs)
                if not covered:
                    self._remove_watch_paths_under(task["abs_path"])

            QApplication.processEvents()
            time.sleep(0.03)
            QApplication.processEvents()

            for task in dir_tasks:
                d = task["directory"]
                if self.project_manager.delete_dsl_directory(d):
                    self.close_directory_tabs(d)
                    success_count += 1

            for task in file_tasks:
                cn, d = task["case_name"], task["directory"]
                covered = any(d == sd or d.startswith(sd + "/") for sd in selected_dirs)
                if covered:
                    continue
                if self.project_manager.delete_dsl_case(cn, d):
                    fk = f"{d}/{cn}" if d else cn
                    self.close_case_tab(fk)
                    success_count += 1
        finally:
            self.file_watcher.blockSignals(False)

        if batch_entries:
            undo_info = {"operation": "delete_dsl_batch", "entries": batch_entries}
            self._push_undo_info(undo_info)

        self.update_project_tree()
        self._sync_file_watcher()
        self.update_status(f"已删除 {success_count} 个项目（可按 Ctrl+Z 撤销）")

    # ==================== DSL 复制/粘贴 ====================

    def copy_dsl_case(self, case_name: str, directory: str) -> None:
        self.clipboard = {"type": "items", "items": [{"type": "file", "case_name": case_name, "directory": directory}]}
        self.update_status(f"已复制Case '{case_name}.dsl'")

    def copy_dsl_directory(self, directory: str) -> None:
        self.clipboard = {"type": "items", "items": [{"type": "directory", "directory": directory}]}
        self.update_status(f"已复制目录 '{directory}'")

    def copy_dsl_items(self, items_data: List[Dict[str, Any]]) -> None:
        clipboard_items = []
        for item_data in items_data:
            if not item_data:
                continue
            if item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path.endswith('.dsl'):
                    cn = PurePosixPath(file_path).stem
                    d = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
                    clipboard_items.append({"type": "file", "case_name": cn, "directory": d})
            elif item_data.get("type") == "directory":
                clipboard_items.append({"type": "directory", "directory": item_data.get("path", "")})
        if clipboard_items:
            self.clipboard = {"type": "items", "items": clipboard_items}
            self.update_status(f"已复制 {len(clipboard_items)} 个项目")

    def paste_dsl_item(self, target_directory: str) -> None:
        if not self.clipboard:
            return

        cb_type = self.clipboard.get("type")
        created_entries: List[Dict[str, Any]] = []

        if cb_type == "file":
            entry = self._paste_single_file(self.clipboard["case_name"], self.clipboard["directory"], target_directory)
            if entry:
                created_entries.append(entry)

        elif cb_type == "directory":
            src = self.clipboard["directory"]
            dn = src.split("/")[-1] if "/" in src else src
            entry = self._paste_single_directory(src, dn, target_directory)
            if entry:
                created_entries.append(entry)

        elif cb_type == "items":
            for item in self.clipboard.get("items", []):
                if item["type"] == "file":
                    entry = self._paste_single_file(item["case_name"], item["directory"], target_directory)
                    if entry:
                        created_entries.append(entry)
                elif item["type"] == "directory":
                    src = item["directory"]
                    dn = src.split("/")[-1] if "/" in src else src
                    entry = self._paste_single_directory(src, dn, target_directory)
                    if entry:
                        created_entries.append(entry)

        if created_entries:
            self._push_undo_info({
                "operation": "paste_dsl_items",
                "entries": created_entries
            })
            self.update_status(f"已粘贴 {len(created_entries)} 个项目（可按 Ctrl+Z 撤销）")

    def _paste_single_file(self, old_case_name: str, source_directory: str, target_directory: str) -> Optional[Dict[str, Any]]:
        """粘贴单个 DSL 文件"""
        source_relative = f"dsl_case/{source_directory}/{old_case_name}.dsl" if source_directory else f"dsl_case/{old_case_name}.dsl"
        source_file = self.project_manager.get_full_path(source_relative)
        if not source_file or not source_file.exists():
            QMessageBox.critical(self, "错误", f"源文件不存在: {old_case_name}.dsl")
            return None

        target_dir = self.project_manager.get_full_path(f"dsl_case/{target_directory}") if target_directory else self.project_manager.get_full_path("dsl_case")
        if not target_dir:
            QMessageBox.critical(self, "错误", "目标目录无效")
            return None
        target_dir.mkdir(parents=True, exist_ok=True)

        new_name = old_case_name
        target_file = target_dir / f"{new_name}.dsl"
        while target_file.exists():
            new_name = f"{new_name}_copy"
            target_file = target_dir / f"{new_name}.dsl"

        shutil.copy2(str(source_file), str(target_file))

        if "dsl_cases" not in self.project_manager.project_config:
            self.project_manager.project_config["dsl_cases"] = []

        relative_path = f"dsl_case/{target_directory}/{new_name}.dsl" if target_directory else f"dsl_case/{new_name}.dsl"
        self.project_manager.project_config["dsl_cases"].append({
            "name": new_name,
            "file": relative_path,
            "directory": target_directory,
            "created_time": datetime.now().isoformat()
        })
        self.project_manager.save_project()
        self.update_project_tree(restore_selection=False)
        self.open_case_modular_editor_with_directory(new_name, target_directory)

        return {
            "kind": "file",
            "case_name": new_name,
            "directory": target_directory
        }

    def _paste_single_directory(self, source_directory: str, dir_name: str, target_directory: str) -> Optional[Dict[str, Any]]:
        """粘贴单个 DSL 目录"""
        source_dir = self.project_manager.get_full_path(f"dsl_case/{source_directory}")
        if not source_dir or not source_dir.exists():
            QMessageBox.critical(self, "错误", f"源目录不存在: {source_directory}")
            return None

        target_dir = self.project_manager.get_full_path(f"dsl_case/{target_directory}") if target_directory else self.project_manager.get_full_path("dsl_case")
        if not target_dir:
            QMessageBox.critical(self, "错误", "目标目录无效")
            return None
        target_dir.mkdir(parents=True, exist_ok=True)

        new_dir_name = dir_name
        new_target_dir = target_dir / new_dir_name
        while new_target_dir.exists():
            new_dir_name = f"{new_dir_name}_copy"
            new_target_dir = target_dir / new_dir_name

        shutil.copytree(str(source_dir), str(new_target_dir))

        if "dsl_cases" not in self.project_manager.project_config:
            self.project_manager.project_config["dsl_cases"] = []
        new_directory = f"{target_directory}/{new_dir_name}" if target_directory else new_dir_name
        self._add_directory_to_config(new_directory, new_target_dir)
        self.project_manager.save_project()
        self.update_project_tree(restore_selection=False)
        QTimer.singleShot(50, lambda: self._highlight_directory_node(new_dir_name, target_directory))
        QTimer.singleShot(50, lambda: self.project_tree.setFocus())

        return {
            "kind": "directory",
            "directory": new_directory
        }

    def _add_directory_to_config(self, directory: str, dir_path: Path) -> None:
        """递归添加目录及其所有文件到项目配置"""
        for item in dir_path.iterdir():
            if item.is_file() and item.suffix == '.dsl':
                case_name = item.stem
                self.project_manager.project_config["dsl_cases"].append({
                    "name": case_name, "file": f"dsl_case/{directory}/{case_name}.dsl",
                    "directory": directory, "created_time": datetime.now().isoformat()
                })
            elif item.is_dir():
                self._add_directory_to_config(f"{directory}/{item.name}", item)

    # ==================== 编辑器与智能提示 ====================

    def setup_modular_editor_completions(self, editor: ModularCaseEditor) -> None:
        """设置模块化编辑器的智能提示"""
        completions = ["sig::", "env::", "sys::"]

        channels = set()
        for dbc_path, mapping_info in self.dbc_parser.can_channel_mapping.items():
            # 兼容新旧格式：新格式为 {"channel": int, "short_name": str}，旧格式直接为 int
            if isinstance(mapping_info, dict):
                channel = mapping_info.get("channel")
            else:
                channel = mapping_info
            if channel is not None:
                channels.add(f"CAN {channel + 1}")
        for channel in sorted(channels):
            completions.append(f"sig::{channel}::")
            completions.append(f"env::{channel}::")

        for dbc_path, db in self.dbc_parser.dbc_files.items():
            channel = self.dbc_parser.get_can_channel_for_dbc(dbc_path)
            if channel is None:
                continue
            for msg in db.messages:
                sig_prefix = f"sig::CAN {channel + 1}::{msg.name}::"
                env_prefix = f"env::CAN {channel + 1}::{msg.name}::"
                completions.append(sig_prefix)
                completions.append(env_prefix)
                for sig in msg.signals:
                    completions.append(f"{sig_prefix}{sig.name}")
                    completions.append(f"{env_prefix}{sig.name}")

        namespaces: Dict[str, List[str]] = {}
        for var in self.dbc_parser.system_variables:
            if "::" in var:
                parts = var.split("::")
                ns = parts[0]
                variable = "::".join(parts[1:])
                if ns not in namespaces:
                    namespaces[ns] = []
                namespaces[ns].append(variable)
            else:
                completions.append(f"sys::{var}")

        for ns in sorted(namespaces):
            completions.append(f"sys::{ns}::")
            for variable in namespaces[ns]:
                completions.append(f"sys::{ns}::{variable}")

        editor.set_completions(completions)

    def update_all_editor_completions(self) -> None:
        for i in range(self.editor_tabs.count()):
            editor = self.editor_tabs.widget(i)
            if isinstance(editor, ModularCaseEditor):
                self.setup_modular_editor_completions(editor)

    def open_case_text_editor(self, case_name: str, directory: str = "") -> None:
        content = self.project_manager.load_dsl_case(case_name, directory)
        if content is None:
            QMessageBox.critical(self, "错误", f"加载Case '{case_name}' 失败\n目录: '{directory}'")
            return

        tab_name = f"{case_name}.dsl"
        file_key = f"{directory}/{case_name}" if directory else case_name

        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key and tab_data.get("editor_type") == "text":
                self.editor_tabs.setCurrentIndex(i)
                return

        editor = DSLTextEditor()
        editor.set_content(content)
        editor.textChanged.connect(self.on_editor_text_changed)

        tab = self.editor_tabs.addTab(editor, tab_name)
        self.editor_tabs.tabBar().setTabData(tab, {"file_key": file_key, "editor_type": "text"})
        self.editor_tabs.setCurrentIndex(tab)

        if file_key not in self.file_editors_map:
            self.file_editors_map[file_key] = []
        self.file_editors_map[file_key].append(editor)

        self.current_case_directory = directory
        self.current_case_name = case_name
        self.current_case_modified = False
        self.update_window_title()
        self.update_status(f"打开Case '{case_name}' (文本编辑器)")

    def open_file_viewer(self, file_name: str, file_type: str) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        full_path = self.project_manager.get_full_path(f"{file_type}/{file_name}")
        if not full_path or not full_path.exists():
            QMessageBox.critical(self, "错误", f"文件不存在: {file_name}")
            return

        file_key = f"viewer:{file_type}:{file_name}"
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            for i in range(self.editor_tabs.count()):
                tab_data = self.editor_tabs.tabBar().tabData(i)
                if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key:
                    self.editor_tabs.setCurrentIndex(i)
                    return

            # 根据文件类型选择编辑器
            is_xml_file = file_name.lower().endswith('.xvp') or file_name.lower().endswith('.vsysvar') or file_name.lower().endswith('.xml')
            is_read_only = file_type in ("dbc_file", "env_dbc", "system_variable")

            if is_xml_file:
                # 使用XML编辑器（带语法高亮）
                editor = XMLTextEditor()
                editor.set_content(content)
                editor.set_file_info(str(full_path), file_name)
                if is_read_only:
                    editor.setReadOnly(True)
                editor.content_changed.connect(self.on_editor_text_changed)
                editor.save_to_file_requested.connect(lambda: self._save_xml_file(editor))
            else:
                # 使用普通DSL编辑器
                editor = DSLTextEditor()
                editor.set_content(content)
                if is_read_only:
                    editor.setReadOnly(True)

            tab = self.editor_tabs.addTab(editor, file_name)
            self.editor_tabs.tabBar().setTabData(tab, {"file_key": file_key, "editor_type": "viewer"})
            self.editor_tabs.setCurrentIndex(tab)
            self.update_status(f"打开文件 '{file_name}'" + (" (只读模式)" if is_read_only else ""))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {e}")

    def _save_xml_file(self, editor: XMLTextEditor) -> None:
        """保存XML文件"""
        if not editor.get_file_path():
            return
        try:
            content = editor.get_content()
            with open(editor.get_file_path(), 'w', encoding='utf-8') as f:
                f.write(content)
            editor.document().setModified(False)
            self.update_status(f"文件 '{editor.get_file_name()}' 已保存")
            self._save_open_files_state()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存文件失败: {e}")

    def open_case_modular_editor(self, file_name: str) -> None:
        """打开Case模块化编辑器（兼容旧调用）"""
        case_name = file_name[:-4] if file_name.endswith('.dsl') else file_name
        content = self.project_manager.load_dsl_case(case_name)
        if content is None:
            QMessageBox.critical(self, "错误", f"加载Case '{case_name}' 失败")
            return

        for i in range(self.editor_tabs.count()):
            if self.editor_tabs.tabText(i) == case_name:
                self.editor_tabs.setCurrentIndex(i)
                return

        editor = ModularCaseEditor(dbc_parser=self.dbc_parser, project_manager=self.project_manager)
        editor.from_dsl(content)
        self.setup_modular_editor_completions(editor)
        editor.content_changed.connect(self.on_editor_text_changed)
        editor.save_to_file_requested.connect(self.save_case)
        editor.status_updated.connect(self.update_status)  # 连接状态更新信号

        tab = self.editor_tabs.addTab(editor, case_name)
        self.editor_tabs.setCurrentIndex(tab)

        if case_name not in self.file_editors_map:
            self.file_editors_map[case_name] = []
        self.file_editors_map[case_name].append(editor)

        self.current_case_name = case_name
        self.current_case_modified = False
        self.update_window_title()
        self.update_status(f"打开Case '{case_name}' (模块化编辑器)")

    def open_case_modular_editor_with_directory(self, case_name: str, directory: str) -> None:
        """打开指定目录中的Case模块化编辑器"""
        content = self.project_manager.load_dsl_case(case_name, directory)
        if content is None:
            QMessageBox.critical(self, "错误", f"加载Case '{case_name}' 失败\n目录: '{directory}'")
            return

        tab_name = case_name
        file_key = f"{directory}/{case_name}" if directory else case_name

        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key and tab_data.get("editor_type") == "modular":
                self.editor_tabs.currentChanged.disconnect(self.on_tab_changed)
                self.editor_tabs.setCurrentIndex(i)
                self.editor_tabs.currentChanged.connect(self.on_tab_changed)
                self._highlight_tree_node(case_name, directory)
                return

        editor = ModularCaseEditor(dbc_parser=self.dbc_parser, project_manager=self.project_manager)
        editor.from_dsl(content)
        self.setup_modular_editor_completions(editor)
        editor.content_changed.connect(self.on_editor_text_changed)
        editor.save_to_file_requested.connect(self.save_case)
        editor.status_updated.connect(self.update_status)  # 连接状态更新信号

        self.editor_tabs.currentChanged.disconnect(self.on_tab_changed)
        tab = self.editor_tabs.addTab(editor, tab_name)
        self.editor_tabs.tabBar().setTabData(tab, {"file_key": file_key, "editor_type": "modular"})
        self.editor_tabs.setCurrentIndex(tab)
        self.editor_tabs.currentChanged.connect(self.on_tab_changed)
        self._highlight_tree_node(case_name, directory)

        if file_key not in self.file_editors_map:
            self.file_editors_map[file_key] = []
        self.file_editors_map[file_key].append(editor)

        self.current_case_directory = directory
        self.current_case_name = case_name
        self.current_case_modified = False
        self.update_window_title()
        self.update_status(f"打开Case '{case_name}' (模块化编辑器)")

    # ==================== 标签管理 ====================

    def close_case_tab(self, file_key: str) -> None:
        for i in range(self.editor_tabs.count() - 1, -1, -1):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key:
                self.editor_tabs.removeTab(i)
                if self.current_case_name == file_key or (file_key and "/" in file_key and self.current_case_name == file_key.split("/")[-1]):
                    self.current_case_name = None
                    self.current_case_modified = False
                    self.update_window_title()

    def close_directory_tabs(self, directory: str) -> None:
        for i in range(self.editor_tabs.count() - 1, -1, -1):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict):
                file_key = tab_data.get("file_key", "")
                if file_key and (file_key.startswith(directory + "/") or file_key == directory):
                    self.editor_tabs.removeTab(i)

    def close_automation_directory_tabs(self, dir_key_prefix: str) -> None:
        """关闭 Automation Cases 目录下的所有标签页"""
        for i in range(self.editor_tabs.count() - 1, -1, -1):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict):
                file_key = tab_data.get("file_key", "")
                if file_key == dir_key_prefix or file_key.startswith(dir_key_prefix + "/"):
                    self.editor_tabs.removeTab(i)

    def close_editor_tab(self, index: int) -> None:
        """关闭编辑器标签"""
        is_current_tab = (index == self.editor_tabs.currentIndex())
        if is_current_tab and self.current_case_modified:
            reply = QMessageBox.question(
                self, "确认", "当前Case有未保存的修改，是否保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_case()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        editor = self.editor_tabs.widget(index)
        if editor:
            self.unregister_editor(editor)
        self.editor_tabs.removeTab(index)

        if self.editor_tabs.count() == 0:
            self.current_case_name = None
            self.current_case_modified = False
            self.update_window_title()

    def on_editor_text_changed(self) -> None:
        self.current_case_modified = True
        self.update_window_title()

    def sync_other_editors(self, case_name: str, content: str, exclude_editor: Any) -> None:
        if case_name not in self.file_editors_map:
            return
        for editor in self.file_editors_map[case_name]:
            if editor is exclude_editor:
                continue
            try:
                if isinstance(editor, ModularCaseEditor):
                    try:
                        editor.content_changed.disconnect(self.on_editor_text_changed)
                    except Exception:
                        pass
                    editor.from_dsl(content)
                    editor.content_changed.connect(self.on_editor_text_changed)
                elif isinstance(editor, DSLTextEditor):
                    try:
                        editor.textChanged.disconnect(self.on_editor_text_changed)
                    except Exception:
                        pass
                    editor.set_content(content)
                    editor.textChanged.connect(self.on_editor_text_changed)
            except Exception as e:
                print(f"同步编辑器时出错: {e}")

    def unregister_editor(self, editor: Any) -> None:
        for case_name, editors in list(self.file_editors_map.items()):
            if editor in editors:
                editors.remove(editor)
                if not editors:
                    del self.file_editors_map[case_name]
                break

    # ==================== 保存 ====================

    def save_case(self) -> None:
        """保存Case"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return

        editor = self.editor_tabs.currentWidget()

        if isinstance(editor, ModularCaseEditor):
            content = editor.to_dsl()
        elif isinstance(editor, DSLTextEditor):
            content = editor.get_content()
        else:
            QMessageBox.warning(self, "警告", "当前标签不是可保存的编辑器")
            return

        tab_index = self.editor_tabs.currentIndex()
        tab_data = self.editor_tabs.tabBar().tabData(tab_index)
        if not tab_data or not isinstance(tab_data, dict):
            QMessageBox.warning(self, "警告", "无法获取文件信息")
            return

        file_key = tab_data.get("file_key", "")
        content = self._ensure_owner_in_dsl(content)

        if file_key and "/" in file_key:
            parts = file_key.split("/")
            case_name = parts[-1]
            directory = "/".join(parts[:-1])
        else:
            case_name = file_key
            directory = self.current_case_directory

        if self.project_manager.add_dsl_case(case_name, content, directory):
            self.current_case_name = case_name
            self.current_case_directory = directory
            self.current_case_modified = False
            self.sync_other_editors(file_key, content, exclude_editor=editor)
            self.update_project_tree()
            self.update_status(f"Case '{case_name}.dsl' 保存成功")
            self.update_window_title()
        else:
            QMessageBox.critical(self, "错误", "保存Case失败")

    def save_case_in_directory(self, directory: str) -> None:
        """保存Case到指定目录（委托给 save_case）"""
        self.save_case()

    def _parse_case_name_from_dsl(self, dsl_content: str) -> Optional[str]:
        lines = dsl_content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('CASE:'):
                case_name = line[5:].strip()
                if case_name:
                    return case_name
        return None

    def _ensure_owner_in_dsl(self, dsl_content: str) -> str:
        """确保 META 中 owner 不为空"""
        lines = dsl_content.split('\n')
        result_lines = []
        for line in lines:
            if not line.strip().startswith('META:'):
                result_lines.append(line)
                continue
            meta = line[5:].strip()
            if re.search(r'(^|\s)owner=\S+', meta):
                result_lines.append(f"META: {meta}")
            elif re.search(r'(^|\s)owner=(?=\s|$)', meta):
                meta = re.sub(r'(^|\s)owner=(?=\s|$)', r'\1owner=Auto', meta)
                result_lines.append(f"META: {meta}")
            else:
                meta = f"{meta} owner=Auto".strip() if meta else "owner=Auto"
                result_lines.append(f"META: {meta}")
        return '\n'.join(result_lines)

    def get_case_name_from_user(self) -> tuple:
        case_name, ok = QInputDialog.getText(self, "输入Case名称", "请输入Case名称:")
        return case_name, ok

    # ==================== 验证 ====================

    def validate_case(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            errors = editor.validate()
        else:
            QMessageBox.warning(self, "警告", "请先打开或创建Case")
            return
        if not errors:
            QMessageBox.information(self, "验证结果", "Case格式验证通过！")
        else:
            error_text = "\n".join(f"- {error}" for error in errors)
            QMessageBox.warning(self, "验证结果", f"发现以下问题:\n\n{error_text}")

    # ==================== AI 助手 ====================

    def start_floating_button(self) -> None:
        try:
            self.floating_button = FloatingButton()

            original_show_settings = ChatAIDialog.show_settings

            def patched_show_settings(self_dialog):
                settings_dialog = APIConfigDialog(None)
                settings_dialog.config_saved.connect(lambda msg: self.update_status(msg))
                if settings_dialog.exec() == QDialog.DialogCode.Accepted:
                    self_dialog.api_config = settings_dialog.config

            ChatAIDialog.show_settings = patched_show_settings

            original_floating_show_settings = FloatingButton.show_settings

            def patched_floating_show_settings(self_floating):
                settings_dialog = APIConfigDialog(None)
                settings_dialog.config_saved.connect(lambda msg: self.update_status(msg))
                settings_dialog.exec()

            FloatingButton.show_settings = patched_floating_show_settings

            self.floating_button.show()
        except Exception as e:
            print(f"启动AI悬浮按钮失败: {e}")

    def open_ai_assistant(self) -> None:
        if self.floating_button is None:
            self.start_floating_button()
        elif not self.floating_button.isVisible():
            self.floating_button.show()
        self.update_status("AI悬浮按钮已显示，双击按钮或右键选择'打开 AI 助手'来使用")

    def open_dbc_converter(self) -> None:
        """打开DBC转换器对话框"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开项目")
            return

        project_config = self.project_manager.project_config
        project_path = self.project_manager.current_project_path

        dialog = DBCConverterDialog(
            self,
            project_config=project_config,
            project_path=project_path
        )
        dialog.exec()

    def open_oss_config(self) -> None:
        dialog = OSSConfigDialog(self.config_manager, self)
        dialog.exec()

    def open_canoe_panel_generator(self) -> None:
        """打开CANoe面板生成对话框"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开项目")
            return

        # 获取面板文件目录
        canoe_panel_dir = self.project_manager.get_panel_dir()
        canoe_panel_dir.mkdir(parents=True, exist_ok=True)

        # 打开对话框
        dialog = CANoePanelDialog(self.project_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取选择的参数
            sysvar_path = dialog.get_selected_sysvar_path()
            selected_variables = dialog.get_selected_variables()

            if sysvar_path and selected_variables:
                # 调用panel_generation.py中的生成函数
                try:
                    from .panel_generation import generation_xvp
                    panel_output_dir = str(canoe_panel_dir)

                    # 执行生成
                    generated_files = generation_xvp(sysvar_path, selected_variables, panel_output_dir)

                    # 更新project.json中的面板文件列表
                    for generated_file in generated_files:
                        # 获取相对路径
                        rel_path = Path(generated_file).relative_to(self.project_manager.current_project_path)
                        file_name = Path(generated_file).name

                        # 从文件名中解析namespace和message信息
                        # 文件名格式: {namespace}_{node}_{message}_panel.xvp
                        parts = file_name.replace("_panel.xvp", "").split("_")
                        namespace = parts[0] if len(parts) > 0 else ""
                        message_name = parts[-1] if len(parts) > 1 else ""

                        self.project_manager.add_panel_file(str(rel_path), namespace, message_name)

                    # 更新项目树
                    self.update_project_tree()
                    self.update_status(f"CANoe面板文件已生成到: {panel_output_dir}")
                    QMessageBox.information(self, "成功", f"CANoe面板文件已生成到:\n{panel_output_dir}\n\n已更新project.json配置")

                except ImportError:
                    QMessageBox.warning(self, "提示", "panel_generation.py 模块尚未创建，请先创建该模块")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"生成面板文件失败: {str(e)}")

    def open_canoe_capl_generator(self) -> None:
        """打开CANoe仿真节点CAPL生成对话框"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开项目")
            return

        # 打开对话框
        dialog = CANoeCAPLDialog(self.project_manager, self.dbc_parser, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取配置数据
            capl_config = dialog.get_capl_config()
            # print(capl_config)

            if capl_config:
                # 调用capl_generation.py中的生成函数
                try:
                    from .capl_generation import generate_capl

                    # 执行生成
                    output_paths = generate_capl(capl_config, self.project_manager.current_project_path)

                    # generate_capl 返回多文件路径列表，状态栏/弹窗只展示数量与目录，避免长 repr 撑爆窗口
                    capl_dir = self.project_manager.current_project_path / "CANoe" / "capl"
                    self.update_status(f"CAPL文件已生成: {len(output_paths)} 个文件于 {capl_dir}")
                    QMessageBox.information(
                        self, "成功",
                        f"已生成 {len(output_paths)} 个 CAPL 文件:\n{capl_dir}"
                    )

                except ImportError:
                    QMessageBox.warning(self, "提示", "capl_generation.py 模块尚未创建，请先创建该模块")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"生成CAPL文件失败: {str(e)}")

    def show_about(self) -> None:
        QMessageBox.about(
            self, "关于 DSL Case Editor",
            "<h3>DSL Case Editor</h3>"
            "<p>版本: 1.0.0</p>"
            "<p>一个基于Qt的DSL测试用例编辑器</p>"
            "<p>用于编写和管理CAN总线测试用例</p>"
        )

    # ==================== 编辑操作 ====================

    def undo(self) -> None:
        """撤销"""
        editor = self.editor_tabs.currentWidget()

        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            focus_widget = self.focusWidget()
            if focus_widget and focus_widget is not self.project_tree:
                if isinstance(editor, ModularCaseEditor):
                    editor.undo()
                elif isinstance(editor, DSLTextEditor):
                    editor.undo()
                return

        if self._undo_stack:
            undo_info = self._undo_stack.pop()
            self._execute_undo(undo_info)
            return

    def _execute_undo(self, undo_info: Dict[str, Any]) -> None:
        operation = undo_info.get("operation")
        handler = {
            "delete_dsl_file": self._undo_delete_dsl_file,
            "delete_dsl_directory": self._undo_delete_dsl_directory,
            "delete_dsl_batch": self._undo_delete_dsl_batch,
            "delete_test_requirement": self._undo_delete_test_requirement,
            "delete_scene_mapping": self._undo_delete_scene_mapping,
            "delete_automation_file": self._undo_delete_automation_file,
            "delete_automation_batch": self._undo_delete_automation_batch,
            "delete_dbc_file": self._undo_delete_dbc_file,
            "delete_env_dbc_file": self._undo_delete_env_dbc_file,
            "delete_system_variable_file": self._undo_delete_system_variable_file,
            "delete_panel_file": self._undo_delete_panel_file,
            "paste_dsl_items": self._undo_paste_dsl_items,
            "paste_automation_items": self._undo_paste_automation_items,
            "delete_test_results_file": self._undo_delete_test_results_file,
            "delete_test_results_directory": self._undo_delete_test_results_directory,
            "delete_test_results_batch": self._undo_delete_test_results_batch,
        }.get(operation)
        if handler:
            handler(undo_info)
            
    def _undo_paste_dsl_items(self, undo_info: Dict[str, Any]) -> None:
        """撤销 DSL 粘贴（文件/目录）"""
        try:
            entries = undo_info.get("entries", [])
            if not entries or not self.project_manager.is_project_open():
                return

            dsl_root = self.project_manager.current_project_path / "dsl_case"
            dir_entries = [e for e in entries if e.get("kind") == "directory"]
            dir_entries.sort(key=lambda e: len(PurePosixPath(e.get("directory", "")).parts), reverse=True)

            deleted_dirs: List[str] = []

            self.file_watcher.blockSignals(True)
            try:
                # 先解绑所有将删除目录的 watcher
                for entry in dir_entries:
                    rel_dir = entry.get("directory", "")
                    if not rel_dir:
                        continue
                    abs_dir = dsl_root / rel_dir
                    if hasattr(self, "_remove_watch_paths_under"):
                        self._remove_watch_paths_under(abs_dir)

                # 先删目录（深层优先）
                for entry in dir_entries:
                    rel_dir = entry.get("directory", "")
                    if not rel_dir:
                        continue
                    if self.project_manager.delete_dsl_directory(rel_dir):
                        self.close_directory_tabs(rel_dir)
                        deleted_dirs.append(rel_dir)

                # 再删未被目录覆盖的文件
                for entry in entries:
                    if entry.get("kind") != "file":
                        continue
                    case_name = entry.get("case_name", "")
                    directory = entry.get("directory", "")
                    if not case_name:
                        continue

                    if any(directory == d or directory.startswith(d + "/") for d in deleted_dirs):
                        continue

                    abs_file = dsl_root / directory / f"{case_name}.dsl" if directory else dsl_root / f"{case_name}.dsl"
                    if hasattr(self, "_remove_watch_paths_under"):
                        self._remove_watch_paths_under(abs_file)

                    if self.project_manager.delete_dsl_case(case_name, directory):
                        file_key = f"{directory}/{case_name}" if directory else case_name
                        self.close_case_tab(file_key)
            finally:
                self.file_watcher.blockSignals(False)

            self.update_project_tree()
            self._sync_file_watcher()
            self.update_status(f"已撤销粘贴 {len(entries)} 个 DSL 项目")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"撤销 DSL 粘贴失败: {e}")
            
    def _undo_paste_automation_items(self, undo_info: Dict[str, Any]) -> None:
        """撤销 automation 粘贴（py_cases/json_cases 文件或目录）"""
        try:
            entries = undo_info.get("entries", [])
            if not entries or not self.project_manager.is_project_open():
                return

            dir_entries = [e for e in entries if e.get("kind") == "directory"]
            dir_entries.sort(key=lambda e: len(PurePosixPath(e.get("path", "")).parts), reverse=True)

            deleted_dirs: List[Tuple[str, str]] = []  # (case_type, rel_dir)

            self.file_watcher.blockSignals(True)
            try:
                # 先解绑并删除目录
                for entry in dir_entries:
                    case_type = entry.get("case_type", "py")
                    rel_dir = entry.get("path", "")
                    if not rel_dir:
                        continue
                    base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
                    abs_dir = base / rel_dir

                    if hasattr(self, "_remove_watch_paths_under"):
                        self._remove_watch_paths_under(abs_dir)

                for entry in dir_entries:
                    case_type = entry.get("case_type", "py")
                    rel_dir = entry.get("path", "")
                    if not rel_dir:
                        continue
                    base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
                    abs_dir = base / rel_dir

                    dir_key_prefix = f"automation:{case_type}:{rel_dir}"
                    self.close_automation_directory_tabs(dir_key_prefix)

                    if abs_dir.exists():
                        shutil.rmtree(abs_dir)
                    deleted_dirs.append((case_type, rel_dir))

                # 再删文件（跳过已被目录删除覆盖的）
                for entry in entries:
                    if entry.get("kind") != "file":
                        continue

                    case_type = entry.get("case_type", "py")
                    rel_path = entry.get("path", "")
                    if not rel_path:
                        continue

                    covered = any(
                        case_type == dct and (rel_path == drel or rel_path.startswith(drel + "/"))
                        for dct, drel in deleted_dirs
                    )
                    if covered:
                        continue

                    base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
                    abs_file = base / rel_path

                    if hasattr(self, "_remove_watch_paths_under"):
                        self._remove_watch_paths_under(abs_file)

                    if abs_file.exists():
                        abs_file.unlink()

                    file_key = f"automation:{case_type}:{rel_path}"
                    self.close_case_tab(file_key)

                    directory = str(abs_file.parent.relative_to(base))
                    directory = "" if directory == "." else directory
                    self.project_manager.remove_automation_case(abs_file.stem, case_type, directory)
            finally:
                self.file_watcher.blockSignals(False)

            self.project_manager.sync_automation_cases()
            self.update_project_tree()
            self._sync_file_watcher()
            self.update_status(f"已撤销粘贴 {len(entries)} 个 Automation 项目")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"撤销 Automation 粘贴失败: {e}")

    def _undo_delete_dsl_file(self, undo_info: Dict[str, Any]) -> None:
        try:
            file_path = Path(undo_info["file_path"])
            content = undo_info["content"]
            directory = undo_info.get("directory", "")
            case_name = undo_info["case_name"]

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            if "dsl_cases" not in self.project_manager.project_config:
                self.project_manager.project_config["dsl_cases"] = []
            existing = [c for c in self.project_manager.project_config["dsl_cases"]
                        if c["name"] == case_name and c.get("directory", "") == directory]
            if not existing:
                relative_path = f"dsl_case/{directory}/{case_name}.dsl" if directory else f"dsl_case/{case_name}.dsl"
                self.project_manager.project_config["dsl_cases"].append({
                    "name": case_name, "file": relative_path,
                    "directory": directory, "created_time": undo_info.get("created_time", "")
                })
                self.project_manager.save_project()

            self.update_project_tree()
            self.update_status(f"已恢复文件 '{case_name}.dsl'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复文件失败: {e}")

    def _undo_delete_dsl_directory(self, undo_info: Dict[str, Any]) -> None:
        try:
            files_info = undo_info["files_info"]
            directory = undo_info["directory"]

            for file_info in files_info:
                fp = Path(file_info["file_path"])
                fp.parent.mkdir(parents=True, exist_ok=True)
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(file_info["content"])

            if "dsl_cases" not in self.project_manager.project_config:
                self.project_manager.project_config["dsl_cases"] = []
            for file_info in files_info:
                cn = file_info["case_name"]
                dp = file_info.get("directory", "")
                rel = f"dsl_case/{dp}/{cn}.dsl" if dp else f"dsl_case/{cn}.dsl"
                existing = [c for c in self.project_manager.project_config["dsl_cases"]
                            if c["name"] == cn and c.get("directory", "") == dp]
                if not existing:
                    self.project_manager.project_config["dsl_cases"].append({
                        "name": cn, "file": rel, "directory": dp,
                        "created_time": file_info.get("created_time", "")
                    })
            self.project_manager.save_project()
            self.update_project_tree()
            self.update_status(f"已恢复目录 '{directory}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复目录失败: {e}")

    def _undo_delete_dsl_batch(self, undo_info: Dict[str, Any]) -> None:
        """撤销批量删除 DSL 文件和目录"""
        try:
            entries = undo_info.get("entries", [])
            restored = 0
            if "dsl_cases" not in self.project_manager.project_config:
                self.project_manager.project_config["dsl_cases"] = []

            for entry in entries:
                if entry["kind"] == "file":
                    fp = Path(entry["file_path"])
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    with open(fp, 'w', encoding='utf-8') as f:
                        f.write(entry["content"])
                    cn = entry["case_name"]
                    d = entry.get("directory", "")
                    existing = [c for c in self.project_manager.project_config["dsl_cases"]
                                if c["name"] == cn and c.get("directory", "") == d]
                    if not existing:
                        rel = f"dsl_case/{d}/{cn}.dsl" if d else f"dsl_case/{cn}.dsl"
                        self.project_manager.project_config["dsl_cases"].append({
                            "name": cn, "file": rel, "directory": d,
                            "created_time": entry.get("created_time", "")
                        })
                    restored += 1
                elif entry["kind"] == "directory":
                    for fi in entry.get("files_info", []):
                        fp = Path(fi["file_path"])
                        fp.parent.mkdir(parents=True, exist_ok=True)
                        with open(fp, 'w', encoding='utf-8') as f:
                            f.write(fi["content"])
                        cn = fi["case_name"]
                        dp = fi.get("directory", "")
                        existing = [c for c in self.project_manager.project_config["dsl_cases"]
                                    if c["name"] == cn and c.get("directory", "") == dp]
                        if not existing:
                            rel = f"dsl_case/{dp}/{cn}.dsl" if dp else f"dsl_case/{cn}.dsl"
                            self.project_manager.project_config["dsl_cases"].append({
                                "name": cn, "file": rel, "directory": dp,
                                "created_time": fi.get("created_time", "")
                            })
                    restored += 1

            self.project_manager.save_project()
            self.update_project_tree()
            self.update_status(f"已恢复 {restored} 个项目")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"批量恢复失败: {e}")

    def _undo_delete_automation_batch(self, undo_info: Dict[str, Any]) -> None:
        """撤销批量删除 Automation Cases 文件和目录"""
        try:
            entries = undo_info.get("entries", [])
            restored = 0
            for entry in entries:
                case_type = entry.get("case_type", "py")
                base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
                if entry["kind"] == "file":
                    full_path = base / entry["file_path"]
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(entry["content"])
                    restored += 1
                elif entry["kind"] == "directory":
                    for fi in entry.get("files", []):
                        full_path = base / fi["rel_path"]
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(fi["content"])
                    restored += 1

            self.project_manager.sync_automation_cases()
            self.update_project_tree()
            self.update_status(f"已恢复 {restored} 个项目")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"批量恢复失败: {e}")

    def _undo_delete_test_requirement(self, undo_info: Dict[str, Any]) -> None:
        try:
            name = undo_info["name"]
            file_content = undo_info.get("file_content")
            relative_path = undo_info["file_path"]
            if file_content:
                full_path = self.project_manager.current_project_path / relative_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(file_content)
            if "test_requirements" not in self.project_manager.project_config:
                self.project_manager.project_config["test_requirements"] = []
            existing = [r for r in self.project_manager.project_config["test_requirements"] if r["name"] == name]
            if not existing:
                self.project_manager.project_config["test_requirements"].append({"name": name, "file": relative_path})
                self.project_manager.save_project()
            self.update_project_tree()
            self.update_status(f"已恢复测试需求文档 '{name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复文档失败: {e}")

    def _undo_delete_scene_mapping(self, undo_info: Dict[str, Any]) -> None:
        try:
            name = undo_info["name"]
            file_content = undo_info.get("file_content")
            relative_path = undo_info["file_path"]
            if file_content:
                full_path = self.project_manager.current_project_path / relative_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(file_content)
            if "scene_mappings" not in self.project_manager.project_config:
                self.project_manager.project_config["scene_mappings"] = []
            existing = [s for s in self.project_manager.project_config["scene_mappings"] if s["name"] == name]
            if not existing:
                self.project_manager.project_config["scene_mappings"].append({"name": name, "file": relative_path})
                self.project_manager.save_project()
            self.update_project_tree()
            self.update_status(f"已恢复场景映射 '{name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复场景映射失败: {e}")

    def _undo_delete_automation_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除 Automation Cases 文件"""
        try:
            file_path = undo_info["file_path"]
            case_type = undo_info["case_type"]
            content = undo_info["content"]
            full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.update_project_tree()
            self.update_status(f"已恢复文件 '{Path(file_path).name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复文件失败: {e}")

    def _undo_delete_dbc_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除DBC文件"""
        try:
            file_path = Path(undo_info["file_path"])
            file_content = undo_info["file_content"]
            file_name = undo_info["file_name"]

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # 更新项目配置
            relative_path = f"CANoe/dbc_file/{file_name}"
            if "canoe" not in self.project_manager.project_config:
                self.project_manager.project_config["canoe"] = {}
            dbc_files = self.project_manager.project_config["canoe"].get("dbc_files", {})
            if isinstance(dbc_files, list):
                if relative_path not in dbc_files:
                    dbc_files.append(relative_path)
            else:
                if relative_path not in dbc_files:
                    dbc_files[relative_path] = {
                        "path": relative_path,
                        "short_name": "",
                        "channel": 0
                    }
            self.project_manager.project_config["canoe"]["dbc_files"] = dbc_files
            self.project_manager.save_project()

            # 重新加载DBC文件
            self.dbc_parser.load_dbc_file(str(file_path))
            self.update_all_editor_completions()
            self.update_project_tree()
            self.update_status(f"已恢复DBC文件 '{file_name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复DBC文件失败: {e}")

    def _undo_delete_env_dbc_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除环境变量DBC文件"""
        try:
            file_path = Path(undo_info["file_path"])
            file_content = undo_info["file_content"]
            file_name = undo_info["file_name"]

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # 更新项目配置
            relative_path = f"CANoe/env_dbc/{file_name}"
            if "canoe" not in self.project_manager.project_config:
                self.project_manager.project_config["canoe"] = {}
            if "env_dbc_files" not in self.project_manager.project_config["canoe"]:
                self.project_manager.project_config["canoe"]["env_dbc_files"] = []
            if relative_path not in self.project_manager.project_config["canoe"]["env_dbc_files"]:
                self.project_manager.project_config["canoe"]["env_dbc_files"].append(relative_path)
            self.project_manager.save_project()

            # 重新加载DBC文件
            self.dbc_parser.load_dbc_file(str(file_path))
            self.update_all_editor_completions()
            self.update_project_tree()
            self.update_status(f"已恢复环境变量DBC文件 '{file_name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复环境变量DBC文件失败: {e}")

    def _undo_delete_system_variable_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除系统变量文件"""
        try:
            file_path = Path(undo_info["file_path"])
            file_content = undo_info["file_content"]
            file_name = undo_info["file_name"]

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # 更新项目配置
            relative_path = f"CANoe/system_variable/{file_name}"
            if "canoe" not in self.project_manager.project_config:
                self.project_manager.project_config["canoe"] = {}
            if "system_variable_files" not in self.project_manager.project_config["canoe"]:
                self.project_manager.project_config["canoe"]["system_variable_files"] = []
            if relative_path not in self.project_manager.project_config["canoe"]["system_variable_files"]:
                self.project_manager.project_config["canoe"]["system_variable_files"].append(relative_path)
            self.project_manager.save_project()

            # 重新加载系统变量文件
            self.dbc_parser.load_system_variables(str(file_path))
            self.update_all_editor_completions()
            self.update_project_tree()
            self.update_status(f"已恢复系统变量文件 '{file_name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复系统变量文件失败: {e}")

    def _undo_delete_panel_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除面板文件"""
        try:
            file_path = Path(undo_info["file_path"])
            file_content = undo_info["file_content"]
            file_name = undo_info["file_name"]
            panel_info = undo_info.get("panel_info")

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # 更新项目配置
            if panel_info:
                # 使用原有的面板信息
                self.project_manager.add_panel_file(
                    panel_info.get("path", f"CANoe/panel_files/{file_name}"),
                    panel_info.get("namespace", ""),
                    panel_info.get("message_name", "")
                )
            else:
                # 从文件名解析信息
                relative_path = f"CANoe/panel_files/{file_name}"
                parts = file_name.replace("_panel.xvp", "").split("_")
                namespace = parts[0] if len(parts) > 0 else ""
                message_name = parts[-1] if len(parts) > 1 else ""
                self.project_manager.add_panel_file(relative_path, namespace, message_name)

            self.update_project_tree()
            self.update_status(f"已恢复面板文件 '{file_name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复面板文件失败: {e}")

    def _undo_delete_test_results_file(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除 Test Results 文件"""
        try:
            file_path = undo_info["file_path"]
            data_type = undo_info["data_type"]
            file_content = undo_info.get("file_content")
            full_path = Path(undo_info["full_path"])

            # 只能恢复有内容的文本文件
            if file_content is None:
                QMessageBox.warning(self, "撤销失败", f"文件 '{Path(file_path).name}' 是二进制文件，无法恢复")
                return

            # 创建目录并恢复文件
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(file_content)

            # 同步测试结果
            self.project_manager.sync_test_results()
            self.update_project_tree()
            self.update_status(f"已恢复文件 '{Path(file_path).name}'")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复文件失败: {e}")

    def _undo_delete_test_results_directory(self, undo_info: Dict[str, Any]) -> None:
        """撤销删除 Test Results 目录"""
        try:
            dir_path = undo_info["dir_path"]
            data_type = undo_info["data_type"]
            files_info = undo_info.get("files_info", [])
            full_path = Path(undo_info["full_path"])

            # 恢复目录中的文件
            restored_count = 0
            skipped_count = 0
            for file_info in files_info:
                rel_path = file_info.get("relative_path")
                content = file_info.get("content")

                if content is None:
                    # 二进制文件无法恢复
                    skipped_count += 1
                    continue

                file_full_path = full_path / rel_path
                file_full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                restored_count += 1

            # 同步测试结果
            self.project_manager.sync_test_results()
            self.update_project_tree()

            if skipped_count > 0:
                self.update_status(f"已恢复目录 '{dir_path}' 中 {restored_count} 个文本文件（{skipped_count} 个二进制文件无法恢复）")
            else:
                self.update_status(f"已恢复目录 '{dir_path}' 中 {restored_count} 个文件")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"恢复目录失败: {e}")

    def _undo_delete_test_results_batch(self, undo_info: Dict[str, Any]) -> None:
        """撤销批量删除 Test Results 文件和目录"""
        try:
            entries = undo_info.get("entries", [])
            if not entries:
                return

            restored_count = 0
            skipped_count = 0

            for entry in entries:
                entry_type = entry.get("type")
                full_path = Path(entry.get("full_path", ""))

                if entry_type == "file":
                    file_content = entry.get("file_content")
                    if file_content is None:
                        skipped_count += 1
                        continue

                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(file_content)
                    restored_count += 1

                elif entry_type == "directory":
                    files_info = entry.get("files_info", [])
                    for file_info in files_info:
                        rel_path = file_info.get("relative_path")
                        content = file_info.get("content")

                        if content is None:
                            skipped_count += 1
                            continue

                        file_full_path = full_path / rel_path
                        file_full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(file_full_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        restored_count += 1

            self.project_manager.sync_test_results()
            self.update_project_tree()

            if skipped_count > 0:
                self.update_status(f"已恢复 {restored_count} 个文本文件（{skipped_count} 个二进制文件无法恢复）")
            else:
                self.update_status(f"已恢复 {restored_count} 个文件")
        except Exception as e:
            QMessageBox.warning(self, "撤销失败", f"批量恢复失败: {e}")

    def _push_undo_info(self, undo_info: Dict[str, Any]) -> None:
        self._undo_stack.append(undo_info)
        if len(self._undo_stack) > self._max_undo_history:
            self._undo_stack.pop(0)

    def redo(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, ModularCaseEditor):
            editor.redo()
        elif isinstance(editor, DSLTextEditor):
            editor.redo()

    def cut(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            editor.cut()

    def copy(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            editor.copy()

    def paste(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            editor.paste()

    def select_all(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, (ModularCaseEditor, DSLTextEditor)):
            editor.selectAll()

    def find(self) -> None:
        editor = self.editor_tabs.currentWidget()
        if isinstance(editor, DSLTextEditor):
            editor.find_bar.show()
        else:
            QMessageBox.information(self, "提示", "查找功能仅支持文本编辑器")

    def closeEvent(self, event) -> None:
        if self.current_case_modified:
            reply = QMessageBox.question(
                self, "确认", "当前Case有未保存的修改，是否保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_case()
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        # 保存当前打开的文件状态
        if self.project_manager.is_project_open():
            self._save_open_files_state()
        if self.floating_button is not None:
            if self.floating_button.ai_dialog is not None and self.floating_button.ai_dialog.isVisible():
                self.floating_button.ai_dialog.close()
            self.floating_button.close()
        event.accept()

    # ==================== Scene 映射 ====================

    def add_scene_mapping(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择场景映射表文件", "", "Excel文件 (*.xlsx *.xls);;所有文件 (*.*)"
        )
        if file_path:
            # 使用文件名（不含扩展名）作为映射表名称
            mapping_name = Path(file_path).stem
            if self.project_manager.add_scene_mapping(mapping_name, file_path):
                self.update_project_tree()
                self.refresh_open_modular_editors_scene_mappings()
                self.update_status(f"场景映射表 '{mapping_name}' 添加成功")
            else:
                QMessageBox.critical(self, "错误", f"添加场景映射表 '{mapping_name}' 失败")

    def open_scene_mapping(self, mapping_name: str) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path = self.project_manager.load_scene_mapping(mapping_name)
        if file_path is None:
            QMessageBox.critical(self, "错误", f"加载场景映射表 '{mapping_name}' 失败")
            return
        try:
            if platform.system() == 'Windows':
                os.startfile(str(file_path))
            elif platform.system() == 'Darwin':
                subprocess.run(['open', str(file_path)])
            else:
                subprocess.run(['xdg-open', str(file_path)])
            self.update_status(f"已使用系统默认程序打开场景映射表 '{mapping_name}'")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {e}")

    def refresh_scene_mapping(self, mapping_name: str) -> None:
        """刷新场景映射表，重新加载数据并更新界面"""
        if not self.project_manager.is_project_open():
            return

        # 刷新所有打开的模块化编辑器中的场景映射
        self.refresh_open_modular_editors_scene_mappings()
        self.update_status(f"场景映射表 '{mapping_name}' 已刷新")

    def delete_scene_mapping(self, mapping_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除场景映射表 '{mapping_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        file_content = None
        relative_path = None
        for scene in self.project_manager.project_config.get("scene_mappings", []):
            if scene["name"] == mapping_name:
                relative_path = scene.get("file", "")
                break
        if relative_path:
            full_path = self.project_manager.current_project_path / relative_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    file_content = f.read()

        undo_info = {"operation": "delete_scene_mapping", "name": mapping_name, "file_path": relative_path, "file_content": file_content}
        self._push_undo_info(undo_info)

        if self.project_manager.delete_scene_mapping(mapping_name):
            self.update_project_tree()
            self.refresh_open_modular_editors_scene_mappings()
            self.update_status(f"场景映射表 '{mapping_name}' 已删除（可按 Ctrl+Z 撤销）")
        else:
            if self._undo_stack and self._undo_stack[-1] is undo_info:
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除场景映射表 '{mapping_name}' 失败")

    def refresh_open_modular_editors_scene_mappings(self) -> None:
        for i in range(self.editor_tabs.count()):
            editor = self.editor_tabs.widget(i)
            if isinstance(editor, ModularCaseEditor):
                try:
                    editor.refresh_scene_mappings()
                except Exception:
                    pass

    # ==================== 测试需求文档 ====================

    def add_test_requirement(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择测试需求文档", "",
            "文档文件 (*.docx *.doc *.pdf *.txt);;Word文档 (*.docx *.doc);;PDF文件 (*.pdf);;文本文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            default_name = Path(file_path).stem
            while True:
                name, ok = QInputDialog.getText(self, "文档名称", "请输入文档名称:", text=default_name)
                if not ok or not name:
                    break
                success, error_msg = self.project_manager.add_test_requirement(name, file_path)
                if success:
                    self.update_project_tree()
                    self.update_status(f"测试需求文档 '{name}' 添加成功")
                    break
                elif "已存在" in error_msg:
                    QMessageBox.warning(self, "提示", error_msg)
                    default_name = name
                else:
                    QMessageBox.critical(self, "错误", error_msg)
                    break

    def open_test_requirement(self, name: str) -> None:
        file_path = self.project_manager.load_test_requirement(name)
        if file_path is None:
            QMessageBox.warning(self, "警告", f"找不到测试需求文档 '{name}'")
            return
        try:
            if platform.system() == 'Windows':
                os.startfile(str(file_path))
            elif platform.system() == 'Darwin':
                subprocess.run(['open', str(file_path)])
            else:
                subprocess.run(['xdg-open', str(file_path)])
            self.update_status(f"已打开测试需求文档 '{name}'")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {e}")

    def delete_test_requirement(self, name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除测试需求文档 '{name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        file_content = None
        relative_path = None
        for req in self.project_manager.project_config.get("test_requirements", []):
            if req["name"] == name:
                relative_path = req.get("file", "")
                break
        if relative_path:
            full_path = self.project_manager.current_project_path / relative_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    file_content = f.read()

        undo_info = {"operation": "delete_test_requirement", "name": name, "file_path": relative_path, "file_content": file_content}
        self._push_undo_info(undo_info)

        if self.project_manager.delete_test_requirement(name):
            self.update_project_tree()
            self.update_status(f"测试需求文档 '{name}' 已删除（可按 Ctrl+Z 撤销）")
        else:
            if self._undo_stack and self._undo_stack[-1] is undo_info:
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除测试需求文档 '{name}' 失败")

    # ==================== DSL -> Automation 转换 ====================

    def convert_single_dsl_to_automation(self, case_name: str, directory: str) -> None:
        self._show_convert_dialog([(case_name, directory)])

    def convert_dsl_to_automation(self, directory: str, convert_all: bool) -> None:
        files_to_convert = []
        if convert_all:
            dsl_structure = self.project_manager.get_dsl_directory_structure()
            self._collect_dsl_files(dsl_structure, "", files_to_convert)
        else:
            dsl_dir = self.project_manager.current_project_path / "dsl_case" / directory
            if dsl_dir.exists():
                self._collect_dsl_files_from_dir(dsl_dir, directory, files_to_convert)
        if not files_to_convert:
            QMessageBox.information(self, "提示", "没有找到需要转换的 DSL 文件")
            return
        self._show_convert_dialog(files_to_convert)

    def _collect_dsl_files(self, node: Dict[str, Any], current_path: str, files: List) -> None:
        for child in node.get("children", []):
            if child["type"] == "file" and child["name"].endswith(".dsl"):
                case_name = Path(child["name"]).stem
                directory = str(Path(child["path"]).parent) if "/" in child["path"] else ""
                files.append((case_name, directory))
            elif child["type"] == "directory":
                new_path = f"{current_path}/{child['name']}" if current_path else child["name"]
                self._collect_dsl_files(child, new_path, files)

    def _collect_dsl_files_from_dir(self, dir_path: Path, relative_path: str, files: List) -> None:
        for item in dir_path.rglob("*.dsl"):
            rel_path = item.relative_to(self.project_manager.current_project_path / "dsl_case")
            case_name = item.stem
            directory = str(rel_path.parent) if rel_path.parent != Path(".") else ""
            files.append((case_name, directory))

    def _show_convert_dialog(self, files: List[Tuple[str, str]]) -> None:
        from .dialogs import ConvertDialog
        dialog = ConvertDialog(len(files), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._execute_conversion(files, dialog.get_options())

    def _execute_conversion(self, files: List[Tuple[str, str]], options: Dict[str, Any]) -> None:
        convert_py = options.get("convert_py", True)
        convert_json = options.get("convert_json", True)

        targets: List[Tuple[str, Any]] = []
        if convert_py:
            targets.append(("py", self._convert_to_py))
        if convert_json:
            targets.append(("json", self._convert_to_json))

        if not targets:
            QMessageBox.information(self, "提示", "请至少选择一种转换类型")
            return

        progress = QProgressDialog("正在转换...", "取消", 0, len(files), self)
        progress.setWindowTitle("转换进度")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        success_count = 0
        skip_count = 0
        error_count = 0
        failed_details: List[Tuple[str, str, str]] = []
        canceled = False

        for i, (case_name, directory) in enumerate(files):
            if progress.wasCanceled():
                canceled = True
                break

            case_display = f"{directory}/{case_name}.dsl" if directory else f"{case_name}.dsl"
            progress.setValue(i)
            progress.setLabelText(f"正在转换: {case_display}")

            try:
                dsl_content = self.project_manager.load_dsl_case(case_name, directory)
                if dsl_content is None:
                    for target_name, _ in targets:
                        error_count += 1
                        failed_details.append((case_display, target_name, "无法加载 DSL 文件"))
                    continue

                for target_name, converter in targets:
                    result, err_msg = converter(case_name, directory, dsl_content, options)
                    if result == "success":
                        success_count += 1
                    elif result == "skip":
                        skip_count += 1
                    else:
                        error_count += 1
                        failed_details.append((case_display, target_name, err_msg or "未知错误"))
            except Exception as e:
                for target_name, _ in targets:
                    error_count += 1
                    failed_details.append((case_display, target_name, str(e)))

        progress.setValue(len(files))
        self.update_project_tree()
        self._refresh_opened_automation_editors()

        status_text = "转换已取消" if canceled else "转换完成"
        result_lines = [
            f"{status_text}！",
            f"成功: {success_count}",
            f"跳过: {skip_count}",
            f"失败: {error_count}",
        ]

        if failed_details:
            result_lines.append("")
            result_lines.append("失败明细（DSL -> 目标类型）:")
            max_show = 20
            for case_display, target_name, reason in failed_details[:max_show]:
                result_lines.append(f"- {case_display} -> {target_name}: {reason}")
            if len(failed_details) > max_show:
                result_lines.append(f"... 还有 {len(failed_details) - max_show} 条失败记录")
            QMessageBox.warning(self, "转换结果", "\n".join(result_lines))
        else:
            QMessageBox.information(self, "转换结果", "\n".join(result_lines))

    def _convert_to_py(self, case_name: str, directory: str, dsl_content: str, options: Dict) -> Tuple[str, str]:
        """转换为 Python 文件，返回 (状态, 错误信息)"""
        target_dir = self.project_manager.current_project_path / "automation_case" / "py_cases"
        if directory:
            target_dir = target_dir / directory
        target_path = target_dir / f"{case_name}.py"

        if target_path.exists():
            action = options.get("exist_action", "ask")
            if action == "skip":
                return "skip", ""
            elif action == "rename":
                new_name, ok = QInputDialog.getText(self, "重命名", f"文件 {case_name}.py 已存在，请输入新名称:", text=case_name)
                if not ok or not new_name:
                    return "skip", ""
                target_path = target_dir / f"{new_name}.py"

        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            from .convert_2_pycase import parse_dsl_case, convert_case_to_python_module
            dsl = parse_dsl_case(dsl_content, fallback_name=case_name)
            py_content = convert_case_to_python_module(dsl)
        except Exception as e:
            return "error", str(e)

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(py_content)
        actual_name = target_path.stem
        dir_path = str(target_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / "py_cases"))
        directory = dir_path if dir_path != "." else ""
        self.project_manager.add_automation_case(actual_name, "py", directory)
        return "success", ""

    def _convert_to_json(self, case_name: str, directory: str, dsl_content: str, options: Dict) -> Tuple[str, str]:
        """转换为 JSON 文件，返回 (状态, 错误信息)"""
        target_dir = self.project_manager.current_project_path / "automation_case" / "json_cases"
        if directory:
            target_dir = target_dir / directory
        target_path = target_dir / f"{case_name}.json"

        if target_path.exists():
            action = options.get("exist_action", "ask")
            if action == "skip":
                return "skip", ""
            elif action == "rename":
                new_name, ok = QInputDialog.getText(self, "重命名", f"文件 {case_name}.json 已存在，请输入新名称:", text=case_name)
                if not ok or not new_name:
                    return "skip", ""
                target_path = target_dir / f"{new_name}.json"

        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            from .convert_2_jsoncase import convert_dsl_to_json
            # 使用当前项目的 project.json 文件路径
            channel_conf_path = str(self.project_manager.current_project_path / "project.json")
            json_text = convert_dsl_to_json(dsl_content=dsl_content, channel_conf_path=channel_conf_path)
            if not json_text:
                return "error", "转换函数返回失败"
        except Exception as e:
            return "error", str(e)

        # 写入 JSON 文件
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(json_text)

        actual_name = target_path.stem
        dir_path = str(target_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / "json_cases"))
        directory = dir_path if dir_path != "." else ""
        self.project_manager.add_automation_case(actual_name, "json", directory)
        return "success", ""

    # ==================== Automation Cases 操作 ====================

    def add_automation_directory(self, parent_path: str) -> None:
        if not self.project_manager.is_project_open():
            return
        dir_name, ok = QInputDialog.getText(self, "新增子目录", "请输入目录名称:")
        if not ok or not dir_name:
            return

        if "/" in parent_path:
            parts = parent_path.split("/")
            case_type = parts[0]
            rel_dir = "/".join(parts[1:]) if len(parts) > 1 else ""
        else:
            case_type = parent_path
            rel_dir = ""

        new_dir = self.project_manager.current_project_path / "automation_case" / case_type
        if rel_dir:
            new_dir = new_dir / rel_dir
        new_dir = new_dir / dir_name

        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            self.update_project_tree()
            self.update_status(f"目录 '{dir_name}' 创建成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建目录失败: {e}")

    def open_automation_file(self, file_path: str, case_type: str) -> None:
        if not self.project_manager.is_project_open():
            return
        full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / file_path
        if not full_path.exists():
            QMessageBox.warning(self, "警告", f"文件不存在: {file_path}")
            return

        file_key = f"automation:{case_type}:{file_path}"
        tab_name = Path(file_path).name
        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key:
                self.editor_tabs.setCurrentIndex(i)
                return

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取文件失败: {e}")
            return

        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(content)
        editor.setFont(QFont("Consolas", 10))

        tab = self.editor_tabs.addTab(editor, tab_name)
        self.editor_tabs.tabBar().setTabData(tab, {"file_key": file_key, "editor_type": "automation"})
        self.editor_tabs.setCurrentIndex(tab)

    def _refresh_opened_automation_editors(self) -> None:
        """刷新已打开的 py/json 编辑器内容"""
        if not self.project_manager.is_project_open():
            return
        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if not isinstance(tab_data, dict) or tab_data.get("editor_type") != "automation":
                continue
            file_key = tab_data.get("file_key", "")
            if not file_key.startswith("automation:"):
                continue
            # 解析 file_key: automation:{case_type}:{file_path}
            parts = file_key.split(":", 2)
            if len(parts) < 3:
                continue
            case_type = parts[1]
            file_path = parts[2]
            full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / file_path
            if not full_path.exists():
                continue
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                editor = self.editor_tabs.widget(i)
                if isinstance(editor, QTextEdit):
                    editor.setPlainText(content)
            except Exception:
                pass

    def delete_automation_file(self, file_path: str, case_type: str) -> None:
        reply = QMessageBox.question(self, "确认删除", f"确定要删除文件 '{Path(file_path).name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / file_path
        file_content = ""
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

        undo_info = {"operation": "delete_automation_file", "file_path": file_path, "case_type": case_type, "content": file_content}
        self._push_undo_info(undo_info)

        try:
            full_path.unlink()
            file_key = f"automation:{case_type}:{file_path}"
            self.close_case_tab(file_key)
            dir_path = str(full_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"))
            directory = dir_path if dir_path != "." else ""
            self.project_manager.remove_automation_case(Path(file_path).stem, case_type, directory)
            self.update_project_tree()
            self.update_status(f"文件 '{Path(file_path).name}' 已删除（可按 Ctrl+Z 撤销）")
        except Exception as e:
            if self._undo_stack and self._undo_stack[-1] is undo_info:
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除文件失败: {e}")
            
    def delete_automation_items(self, items_data: List[Dict[str, Any]]) -> None:
        """批量删除 Automation Cases 文件和目录（覆盖 py_cases/json_cases 子目录）"""
        if isinstance(items_data, bool) or items_data is None:
            # 防御式处理：兼容 QAction.triggered(bool) 传参
            items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in self.project_tree.selectedItems()]

        if not isinstance(items_data, list):
            return

        items_data = [d for d in items_data if isinstance(d, dict)]
        if not items_data:
            return

        file_count = sum(1 for d in items_data if d and d.get("type") == "automation_file")
        dir_count = sum(1 for d in items_data if d and d.get("type") == "automation_directory")

        message = "确定要删除以下项目吗？\n\n"
        if file_count > 0:
            message += f"文件: {file_count} 个\n"
        if dir_count > 0:
            message += f"目录: {dir_count} 个\n"

        reply = QMessageBox.question(
            self, "确认删除", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        batch_entries: List[Dict[str, Any]] = []
        delete_tasks: List[Dict[str, Any]] = []

        for item_data in items_data:
            if not item_data:
                continue
            item_type = item_data.get("type")
            case_type = item_data.get("case_type", "py")
            base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"

            try:
                if item_type == "automation_file":
                    fp = base / item_data.get("path", "")
                    if fp.exists():
                        with open(fp, 'r', encoding='utf-8') as f:
                            content = f.read()
                        batch_entries.append({
                            "kind": "file",
                            "file_path": item_data.get("path", ""),
                            "case_type": case_type,
                            "content": content
                        })
                        delete_tasks.append({
                            "type": "automation_file",
                            "path": item_data.get("path", ""),
                            "case_type": case_type,
                            "base": base,
                            "fp": fp
                        })

                elif item_type == "automation_directory":
                    dp = base / item_data.get("path", "")
                    if dp.exists():
                        dir_files = []
                        for child_file in dp.rglob("*"):
                            if child_file.is_file():
                                rel = str(child_file.relative_to(base))
                                with open(child_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                dir_files.append({"rel_path": rel, "content": content})
                        batch_entries.append({
                            "kind": "directory",
                            "dir_path": item_data.get("path", ""),
                            "case_type": case_type,
                            "files": dir_files
                        })
                        delete_tasks.append({
                            "type": "automation_directory",
                            "path": item_data.get("path", ""),
                            "case_type": case_type,
                            "base": base,
                            "dp": dp
                        })
            except Exception:
                pass

        success_count = 0
        deleted_dirs_norm: List[str] = []

        # 目录先删（深层优先）
        dir_tasks = [t for t in delete_tasks if t["type"] == "automation_directory"]
        dir_tasks.sort(key=lambda t: len(Path(t["path"]).parts), reverse=True)

        # 文件后删（已被目录覆盖的文件跳过）
        file_tasks = [t for t in delete_tasks if t["type"] == "automation_file"]

        self.file_watcher.blockSignals(True)
        try:
            # 先解绑所有将被删除目录的 watcher
            for task in dir_tasks:
                self._remove_watch_paths_under(task["dp"])

            # 再解绑需要单独删除文件的 watcher（不在将删目录下）
            for task in file_tasks:
                fp: Path = task["fp"]
                fp_norm = os.path.normcase(os.path.normpath(str(fp)))
                covered = False
                for d_task in dir_tasks:
                    d_norm = os.path.normcase(os.path.normpath(str(d_task["dp"])))
                    if fp_norm == d_norm or fp_norm.startswith(d_norm + os.sep):
                        covered = True
                        break
                if not covered:
                    self._remove_watch_paths_under(fp)

            QApplication.processEvents()
            time.sleep(0.03)
            QApplication.processEvents()

            for task in dir_tasks:
                dp: Path = task["dp"]
                try:
                    dir_key_prefix = f"automation:{task['case_type']}:{task['path']}"
                    self.close_automation_directory_tabs(dir_key_prefix)
                    if dp.exists():
                        shutil.rmtree(dp)
                    deleted_dirs_norm.append(os.path.normcase(os.path.normpath(str(dp))))
                    success_count += 1
                except Exception:
                    pass

            for task in file_tasks:
                fp: Path = task["fp"]
                fp_norm = os.path.normcase(os.path.normpath(str(fp)))
                if any(fp_norm == d or fp_norm.startswith(d + os.sep) for d in deleted_dirs_norm):
                    continue
                try:
                    if fp.exists():
                        fp.unlink()
                    file_key = f"automation:{task['case_type']}:{task['path']}"
                    self.close_case_tab(file_key)

                    dir_path = str(fp.parent.relative_to(task["base"]))
                    directory = dir_path if dir_path != "." else ""
                    self.project_manager.remove_automation_case(fp.stem, task["case_type"], directory)
                    success_count += 1
                except Exception:
                    pass
        finally:
            self.file_watcher.blockSignals(False)

        if batch_entries:
            undo_info = {"operation": "delete_automation_batch", "entries": batch_entries}
            self._push_undo_info(undo_info)

        self.project_manager.sync_automation_cases()
        self.update_project_tree()
        self._sync_file_watcher()
        self.update_status(f"已删除 {success_count} 个项目（可按 Ctrl+Z 撤销）")

    def delete_automation_directory(self, dir_path: str, case_type: str) -> None:
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除目录 '{dir_path}' 及其所有内容吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / dir_path
        try:
            dir_key_prefix = f"automation:{case_type}:{dir_path}"
            self.close_automation_directory_tabs(dir_key_prefix)

            self.file_watcher.blockSignals(True)
            try:
                self._remove_watch_paths_under(full_path)
                QApplication.processEvents()
                time.sleep(0.03)
                QApplication.processEvents()
                if full_path.exists():
                    shutil.rmtree(full_path)
            finally:
                self.file_watcher.blockSignals(False)

            self.project_manager.sync_automation_cases()
            self.update_project_tree()
            self._sync_file_watcher()
            self.update_status(f"目录 '{dir_path}' 已删除")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除目录失败: {e}")

    def rename_automation_file(self, file_path: str, case_type: str) -> None:
        old_name = Path(file_path).stem
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新名称:", text=old_name)
        if not ok or not new_name:
            return
        old_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / file_path
        new_path = old_path.parent / f"{new_name}{old_path.suffix}"
        try:
            old_path.rename(new_path)
            dir_path = str(old_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"))
            directory = dir_path if dir_path != "." else ""
            self.project_manager.rename_automation_case_in_config(old_name, new_name, case_type, directory)
            self.update_project_tree()
            self.update_status(f"文件已重命名为 '{new_name}'")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重命名失败: {e}")

    def rename_automation_directory(self, dir_path: str, case_type: str) -> None:
        old_name = Path(dir_path).name
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新目录名:", text=old_name)
        if not ok or not new_name:
            return
        old_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / dir_path
        new_path = old_path.parent / new_name
        try:
            old_path.rename(new_path)
            self.project_manager.sync_automation_cases()
            self.update_project_tree()
            self.update_status(f"目录已重命名为 '{new_name}'")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重命名失败: {e}")

    def copy_automation_file(self, file_path: str, case_type: str) -> None:
        self.clipboard = {"type": "automation_file", "file_path": file_path, "case_type": case_type}
        self.update_status(f"已复制文件 '{Path(file_path).name}'")

    def copy_automation_directory(self, dir_path: str, case_type: str) -> None:
        self.clipboard = {"type": "automation_directory", "dir_path": dir_path, "case_type": case_type}
        self.update_status(f"已复制目录 '{dir_path}'")
        
    def copy_automation_items(self, items_data: List[Dict[str, Any]]) -> None:
        """复制多个 Automation Cases 文件/目录到剪贴板"""
        clipboard_items = []
        for item_data in items_data:
            if not item_data:
                continue
            item_type = item_data.get("type")
            if item_type == "automation_file":
                clipboard_items.append({
                    "kind": "file",
                    "path": item_data.get("path", ""),
                    "case_type": item_data.get("case_type", "py")
                })
            elif item_type == "automation_directory":
                clipboard_items.append({
                    "kind": "directory",
                    "path": item_data.get("path", ""),
                    "case_type": item_data.get("case_type", "py")
                })
        if clipboard_items:
            self.clipboard = {"type": "automation_items", "items": clipboard_items}
            self.update_status(f"已复制 {len(clipboard_items)} 个项目")

    def paste_automation_item(self, target_dir: str, case_type: str) -> None:
        """粘贴 Automation Cases 文件/目录，支持单项和多项，并支持 Ctrl+Z 撤销粘贴"""
        if not self.clipboard:
            return

        try:
            base_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
            target_path = base_path / target_dir if target_dir else base_path

            items_to_paste: List[Dict[str, Any]] = []
            cb_type = self.clipboard.get("type")

            if cb_type == "automation_file":
                items_to_paste.append({
                    "kind": "file",
                    "path": self.clipboard["file_path"],
                    "case_type": self.clipboard.get("case_type", case_type)
                })
            elif cb_type == "automation_directory":
                items_to_paste.append({
                    "kind": "directory",
                    "path": self.clipboard["dir_path"],
                    "case_type": self.clipboard.get("case_type", case_type)
                })
            elif cb_type == "automation_items":
                items_to_paste = list(self.clipboard.get("items", []))
            else:
                return

            new_entries: List[Dict[str, str]] = []

            for item in items_to_paste:
                src_case_type = item.get("case_type", case_type)
                src_base = self.project_manager.current_project_path / "automation_case" / f"{src_case_type}_cases"

                if item["kind"] == "file":
                    src_path = src_base / item["path"]
                    if not src_path.exists():
                        continue

                    suffix = src_path.suffix
                    new_stem = f"{src_path.stem}_copy"
                    dst_path = target_path / f"{new_stem}{suffix}"
                    while dst_path.exists():
                        new_stem = f"{new_stem}_copy"
                        dst_path = target_path / f"{new_stem}{suffix}"

                    target_path.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_path), str(dst_path))

                    dst_name = dst_path.name
                    rel_path = f"{target_dir}/{dst_name}" if target_dir else dst_name
                    new_entries.append({
                        "kind": "file",
                        "path": rel_path,
                        "case_type": case_type
                    })

                elif item["kind"] == "directory":
                    src_path = src_base / item["path"]
                    if not src_path.exists():
                        continue

                    new_dir_name = f"{src_path.name}_copy"
                    dst_path = target_path / new_dir_name
                    while dst_path.exists():
                        new_dir_name = f"{new_dir_name}_copy"
                        dst_path = target_path / new_dir_name

                    shutil.copytree(str(src_path), str(dst_path))
                    rel_path = f"{target_dir}/{new_dir_name}" if target_dir else new_dir_name
                    new_entries.append({
                        "kind": "directory",
                        "path": rel_path,
                        "case_type": case_type
                    })

            self.project_manager.sync_automation_cases()
            self.update_project_tree(restore_selection=False)

            if len(new_entries) == 1:
                entry = new_entries[0]
                if entry["kind"] == "file":
                    QTimer.singleShot(50, lambda p=entry["path"], c=entry["case_type"]: self._highlight_automation_node(p, c))
                else:
                    QTimer.singleShot(50, lambda p=entry["path"], c=entry["case_type"]: self._highlight_automation_directory_node(p, c))

            QTimer.singleShot(50, lambda: self.project_tree.setFocus())

            if new_entries:
                self._push_undo_info({
                    "operation": "paste_automation_items",
                    "entries": new_entries
                })
                count = len(new_entries)
                self.update_status("粘贴成功" + (f"（{count} 个项目，可按 Ctrl+Z 撤销）" if count > 1 else "（可按 Ctrl+Z 撤销）"))
            else:
                self.update_status("粘贴完成（未产生新项目）")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"粘贴失败: {e}")

    # ==================== Test Results 相关方法 ====================

    # Data type mapping constants
    _DATA_TYPE_KEY_MAP = {
        "trace_data": ("trace data", "trace"),
        "record_data": ("record data", "record"),
        "log_data": ("log data", "log"),
        "report_data": ("report data", "report")
    }
    _DATA_TYPE_DIR_MAP = {
        "trace": "trace data",
        "record": "record data",
        "log": "log data",
        "report": "report data"
    }

    def open_test_results_file(self, file_path: str, data_type: str) -> None:
        """打开 Test Results 文件"""
        dir_name = self._DATA_TYPE_DIR_MAP.get(data_type, "trace data")
        full_path = self.project_manager.current_project_path / "Test Results" / dir_name / file_path

        if not full_path.exists():
            QMessageBox.warning(self, "Warning", f"File not found: {full_path}")
            return

        file_name = Path(file_path).name

        if data_type == "log":
            # Log files: open in text editor
            self.open_text_file_viewer(str(full_path), file_name)
        elif data_type == "report":
            # HTML files: open in text editor by default
            self.open_text_file_viewer(str(full_path), file_name)
        elif data_type in ("trace", "record"):
            # Binary files: not supported for direct opening
            QMessageBox.information(self, "Info",
                f"'{file_name}' is a binary file and cannot be opened directly in the editor.\n\n"
                f"You can use external tools to view this file:\n"
                f"- trace data (.blf): Use CANoe or Vector tools\n"
                f"- record data (.record): Use appropriate analysis tools")

    def open_text_file_viewer(self, file_path: str, file_name: str) -> None:
        """Open a text file in a simple viewer/editor tab"""
        # Check if already open
        file_key = file_path
        for i in range(self.editor_tabs.count()):
            tab_data = self.editor_tabs.tabBar().tabData(i)
            if isinstance(tab_data, dict) and tab_data.get("file_key") == file_key:
                self.editor_tabs.setCurrentIndex(i)
                return

        # Create a simple text editor for viewing
        from PyQt6.QtWidgets import QTextEdit
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            text_edit.setPlainText(content)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to read file: {e}")
            return

        # Add tab
        tab_index = self.editor_tabs.addTab(text_edit, file_name)
        self.editor_tabs.tabBar().setTabData(tab_index, {
            "file_key": file_key,
            "file_path": file_path,
            "type": "text_viewer",
            "editor_type": "test_results"
        })
        self.editor_tabs.setCurrentIndex(tab_index)

        # Add button to open in browser for HTML files
        if file_name.endswith(".html"):
            # Store reference for the button
            text_edit._file_path = file_path
            text_edit._parent_window = self

    def open_html_in_browser(self, file_path: str) -> None:
        """Open HTML file in external browser (Edge)"""
        import subprocess
        try:
            # Use Edge to open the HTML file
            subprocess.run(["start", "msedge", file_path], shell=True, check=False)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to open in Edge: {e}")
            # Fallback: try default browser
            try:
                import webbrowser
                webbrowser.open(file_path)
            except Exception as e2:
                QMessageBox.critical(self, "Error", f"Failed to open file: {e2}")

    def add_test_results_directory(self, parent_path: str) -> None:
        """添加 Test Results 子目录"""
        if not self.project_manager.is_project_open():
            return

        # 解析 parent_path: 可能是 "trace_data", "record_data", "log_data", "report_data", 或带子目录
        if "/" in parent_path:
            parts = parent_path.split("/", 1)
            data_type_key = parts[0]
            rel_dir = parts[1]
        else:
            data_type_key = parent_path
            rel_dir = ""

        # 转换 data_type_key 为实际目录名
        dir_name, data_type = self._DATA_TYPE_KEY_MAP.get(data_type_key, ("trace data", "trace"))

        dir_name_input, ok = QInputDialog.getText(self, "新建目录", "请输入目录名称:")
        if not ok or not dir_name_input:
            return

        new_dir = self.project_manager.current_project_path / "Test Results" / dir_name
        if rel_dir:
            new_dir = new_dir / rel_dir
        new_dir = new_dir / dir_name_input

        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            self.update_project_tree()
            self.update_status(f"目录 '{dir_name_input}' 创建成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建目录失败: {e}")

    def delete_test_results_file(self, file_path: str, data_type: str) -> None:
        """删除 Test Results 文件"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除文件 '{Path(file_path).name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        dir_name = self._DATA_TYPE_DIR_MAP.get(data_type, "trace data")
        full_path = self.project_manager.current_project_path / "Test Results" / dir_name / file_path

        try:
            # 读取文件内容用于撤销（只对文本文件）
            file_content = None
            if full_path.exists() and full_path.suffix in (".log", ".html"):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except Exception:
                    pass

            # 记录撤销信息
            undo_info = {
                "operation": "delete_test_results_file",
                "file_path": file_path,
                "data_type": data_type,
                "file_content": file_content,
                "full_path": str(full_path)
            }
            self._push_undo_info(undo_info)

            if full_path.exists():
                full_path.unlink()
            self.project_manager.remove_test_results_item(Path(file_path).stem, data_type,
                                                          str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else "")
            self.update_project_tree()
            self.update_status(f"文件 '{Path(file_path).name}' 已删除（可按 Ctrl+Z 撤销）")
        except Exception as e:
            # 删除失败时移除撤销记录
            if self._undo_stack and self._undo_stack[-1].get("operation") == "delete_test_results_file":
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除文件失败: {e}")

    def delete_test_results_directory(self, dir_path: str, data_type: str) -> None:
        """删除 Test Results 目录"""
        reply = QMessageBox.question(self, "确认删除", f"确定要删除目录 '{dir_path}' 及其所有内容吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        dir_name = self._DATA_TYPE_DIR_MAP.get(data_type, "trace data")
        full_path = self.project_manager.current_project_path / "Test Results" / dir_name / dir_path

        try:
            # 收集目录中所有文件的内容用于撤销（只对文本文件）
            files_info = []
            if full_path.exists() and full_path.is_dir():
                for f in full_path.rglob("*"):
                    if f.is_file():
                        # 只保存文本文件内容
                        if f.suffix in (".log", ".html"):
                            try:
                                with open(f, 'r', encoding='utf-8') as file:
                                    content = file.read()
                                rel_path = f.relative_to(full_path)
                                files_info.append({
                                    "relative_path": str(rel_path),
                                    "content": content
                                })
                            except Exception:
                                pass
                        else:
                            # 二进制文件只记录路径，不保存内容
                            rel_path = f.relative_to(full_path)
                            files_info.append({
                                "relative_path": str(rel_path),
                                "content": None  # 二进制文件无法撤销
                            })

            # 记录撤销信息
            undo_info = {
                "operation": "delete_test_results_directory",
                "dir_path": dir_path,
                "data_type": data_type,
                "files_info": files_info,
                "full_path": str(full_path)
            }
            self._push_undo_info(undo_info)

            if full_path.exists() and full_path.is_dir():
                shutil.rmtree(full_path)
            self.project_manager.sync_test_results()
            self.update_project_tree()
            self.update_status(f"目录 '{dir_path}' 已删除（可按 Ctrl+Z 撤销文本文件）")
        except Exception as e:
            # 删除失败时移除撤销记录
            if self._undo_stack and self._undo_stack[-1].get("operation") == "delete_test_results_directory":
                self._undo_stack.pop()
            QMessageBox.critical(self, "错误", f"删除目录失败: {e}")

    def delete_test_results_items(self, items_data: List[Dict[str, Any]]) -> None:
        """批量删除 Test Results 文件和目录"""
        if isinstance(items_data, bool) or items_data is None:
            items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in self.project_tree.selectedItems()]

        if not isinstance(items_data, list):
            return

        items_data = [d for d in items_data if isinstance(d, dict)]
        if not items_data:
            return

        file_count = sum(1 for d in items_data if d and d.get("type") == "test_results_file")
        dir_count = sum(1 for d in items_data if d and d.get("type") == "test_results_directory")

        message = "确定要删除以下项目吗？\n\n"
        if file_count > 0:
            message += f"文件: {file_count} 个\n"
        if dir_count > 0:
            message += f"目录: {dir_count} 个\n"

        reply = QMessageBox.question(
            self, "确认删除", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 收集所有被删除项目的信息用于撤销
        batch_entries = []
        success_count = 0

        for item_data in items_data:
            if not item_data:
                continue
            item_type = item_data.get("type")
            data_type = item_data.get("data_type", "trace")
            dir_name = self._DATA_TYPE_DIR_MAP.get(data_type, "trace data")
            base = self.project_manager.current_project_path / "Test Results" / dir_name

            try:
                if item_type == "test_results_file":
                    fp = base / item_data.get("path", "")
                    if fp.exists():
                        # 读取文件内容用于撤销（只对文本文件）
                        file_content = None
                        if fp.suffix in (".log", ".html"):
                            try:
                                with open(fp, 'r', encoding='utf-8') as f:
                                    file_content = f.read()
                            except Exception:
                                pass

                        batch_entries.append({
                            "type": "file",
                            "file_path": item_data.get("path", ""),
                            "data_type": data_type,
                            "full_path": str(fp),
                            "file_content": file_content
                        })
                        fp.unlink()
                        success_count += 1
                elif item_type == "test_results_directory":
                    dp = base / item_data.get("path", "")
                    if dp.exists() and dp.is_dir():
                        # 收集目录中文件信息
                        files_info = []
                        for f in dp.rglob("*"):
                            if f.is_file():
                                if f.suffix in (".log", ".html"):
                                    try:
                                        with open(f, 'r', encoding='utf-8') as file:
                                            content = file.read()
                                        rel_path = f.relative_to(dp)
                                        files_info.append({
                                            "relative_path": str(rel_path),
                                            "content": content
                                        })
                                    except Exception:
                                        pass
                                else:
                                    rel_path = f.relative_to(dp)
                                    files_info.append({
                                        "relative_path": str(rel_path),
                                        "content": None
                                    })

                        batch_entries.append({
                            "type": "directory",
                            "dir_path": item_data.get("path", ""),
                            "data_type": data_type,
                            "full_path": str(dp),
                            "files_info": files_info
                        })
                        shutil.rmtree(dp)
                        success_count += 1
            except Exception:
                pass

        # 记录撤销信息
        if batch_entries:
            undo_info = {"operation": "delete_test_results_batch", "entries": batch_entries}
            self._push_undo_info(undo_info)

        self.project_manager.sync_test_results()
        self.update_project_tree()
        self.update_status(f"已删除 {success_count} 个项目（可按 Ctrl+Z 撤销文本文件）")

    def copy_test_results_file(self, file_path: str, data_type: str) -> None:
        """复制 Test Results 文件"""
        self.clipboard = {
            "type": "test_results_file",
            "file_path": file_path,
            "data_type": data_type
        }
        self.update_status(f"已复制文件 '{Path(file_path).name}'")

    def copy_test_results_directory(self, dir_path: str, data_type: str) -> None:
        """复制 Test Results 目录"""
        self.clipboard = {
            "type": "test_results_directory",
            "dir_path": dir_path,
            "data_type": data_type
        }
        self.update_status(f"已复制目录 '{dir_path}'")

    def copy_test_results_items(self, items_data: List[Dict[str, Any]]) -> None:
        """多选复制 Test Results 项目"""
        if isinstance(items_data, bool) or items_data is None:
            items_data = [si.data(0, Qt.ItemDataRole.UserRole) for si in self.project_tree.selectedItems()]

        clipboard_items = []
        for item_data in items_data:
            if not item_data:
                continue
            item_type = item_data.get("type")
            if item_type == "test_results_file":
                clipboard_items.append({
                    "kind": "file",
                    "path": item_data.get("path", ""),
                    "data_type": item_data.get("data_type", "trace")
                })
            elif item_type == "test_results_directory":
                clipboard_items.append({
                    "kind": "directory",
                    "path": item_data.get("path", ""),
                    "data_type": item_data.get("data_type", "trace")
                })
        if clipboard_items:
            self.clipboard = {"type": "test_results_items", "items": clipboard_items}
            self.update_status(f"已复制 {len(clipboard_items)} 个项目")

    def paste_test_results_item(self, target_dir: str, data_type: str) -> None:
        """粘贴 Test Results 文件/目录"""
        if not self.clipboard:
            return

        try:
            dir_name = "trace data" if data_type == "trace" else "record data"
            base_path = self.project_manager.current_project_path / "Test Results" / dir_name
            target_path = base_path / target_dir if target_dir else base_path

            items_to_paste: List[Dict[str, Any]] = []
            cb_type = self.clipboard.get("type")

            if cb_type == "test_results_file":
                items_to_paste.append({
                    "kind": "file",
                    "path": self.clipboard["file_path"],
                    "data_type": self.clipboard.get("data_type", data_type)
                })
            elif cb_type == "test_results_directory":
                items_to_paste.append({
                    "kind": "directory",
                    "path": self.clipboard["dir_path"],
                    "data_type": self.clipboard.get("data_type", data_type)
                })
            elif cb_type == "test_results_items":
                items_to_paste = list(self.clipboard.get("items", []))
            else:
                return

            new_entries: List[Dict[str, str]] = []

            for item in items_to_paste:
                src_data_type = item.get("data_type", data_type)
                src_dir_name = "trace data" if src_data_type == "trace" else "record data"
                src_base = self.project_manager.current_project_path / "Test Results" / src_dir_name

                if item["kind"] == "file":
                    src_path = src_base / item["path"]
                    if not src_path.exists():
                        continue

                    suffix = src_path.suffix
                    new_stem = f"{src_path.stem}_copy"
                    dst_path = target_path / f"{new_stem}{suffix}"
                    while dst_path.exists():
                        new_stem = f"{new_stem}_copy"
                        dst_path = target_path / f"{new_stem}{suffix}"

                    target_path.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_path), str(dst_path))

                    dst_name = dst_path.name
                    rel_path = f"{target_dir}/{dst_name}" if target_dir else dst_name
                    new_entries.append({
                        "kind": "file",
                        "path": rel_path,
                        "data_type": data_type
                    })

                elif item["kind"] == "directory":
                    src_path = src_base / item["path"]
                    if not src_path.exists():
                        continue

                    new_dir_name = f"{src_path.name}_copy"
                    dst_path = target_path / new_dir_name
                    while dst_path.exists():
                        new_dir_name = f"{new_dir_name}_copy"
                        dst_path = target_path / new_dir_name

                    shutil.copytree(str(src_path), str(dst_path))
                    rel_path = f"{target_dir}/{new_dir_name}" if target_dir else new_dir_name
                    new_entries.append({
                        "kind": "directory",
                        "path": rel_path,
                        "data_type": data_type
                    })

            self.project_manager.sync_test_results()
            self.update_project_tree(restore_selection=False)

            if new_entries:
                count = len(new_entries)
                self.update_status("粘贴成功" + (f"（{count} 个项目）" if count > 1 else ""))
            else:
                self.update_status("粘贴完成（未产生新项目）")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"粘贴失败: {e}")

    def rename_test_results_directory(self, dir_path: str, data_type: str) -> None:
        """重命名 Test Results 目录"""
        if not self.project_manager.is_project_open():
            return

        old_name = Path(dir_path).name if dir_path else ""
        new_name, ok = QInputDialog.getText(self, "重命名目录", "请输入新目录名称:", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return

        dir_name = "trace data" if data_type == "trace" else "record data"
        base = self.project_manager.current_project_path / "Test Results" / dir_name
        old_path = base / dir_path
        parent_path = old_path.parent
        new_path = parent_path / new_name

        if new_path.exists():
            QMessageBox.warning(self, "警告", f"目录 '{new_name}' 已存在")
            return

        try:
            old_path.rename(new_path)
            self.project_manager.sync_test_results()
            self.update_project_tree()
            self.update_status(f"目录已重命名为 '{new_name}'")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重命名失败: {e}")

    def replay_file(self, file_path: str, data_type: str) -> None:
        """回放 Test Results 文件（调用用户自定义 replay 函数）"""
        if not self.project_manager.is_project_open():
            return

        dir_name = "trace data" if data_type == "trace" else "record data"
        full_path = self.project_manager.current_project_path / "Test Results" / dir_name / file_path
        project_path = self.project_manager.current_project_path

        if not full_path.exists():
            QMessageBox.warning(self, "警告", f"文件不存在: {file_path}")
            return

        # 调用用户自定义的 replay 函数
        # 参数：文件路径、data_type、项目路径
        try:
            self.replay(str(full_path), data_type, str(project_path))
        except NameError:
            QMessageBox.warning(self, "警告", "replay 函数未定义，请先实现 replay 函数")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"回放失败: {e}")
            
    def replay(self, path, data_type, project_path):
        pass

    # ==================== Automation 相关方法 ====================

    def open_preset_setting(self) -> None:
        """打开预设设置对话框"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开项目")
            return

        from .dialogs import PresetSettingDialog
        dlg = PresetSettingDialog(self.project_manager, self.dbc_parser, self)
        dlg.exec()

    def open_template_setting(self) -> None:
        """打开模板设置对话框"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开项目")
            return

        from .dialogs import TemplateSettingDialog
        dlg = TemplateSettingDialog(self.project_manager, self.dbc_parser, self)
        dlg.templates_saved.connect(self._refresh_all_templates)
        dlg.exec()

    def open_ecu_record_config(self) -> None:
        """Open ECU Record configuration dialog"""
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "Warning", "Please open a project first")
            return

        from .dialogs import ECURecordDialog
        dlg = ECURecordDialog(self.project_manager, self)
        dlg.exec()

    def _refresh_all_templates(self) -> None:
        """刷新所有编辑器中的模板列表"""
        # 遍历所有打开的DSL编辑器标签页
        for i in range(self.editor_tabs.count()):
            editor = self.editor_tabs.widget(i)
            if hasattr(editor, 'refresh_all_templates'):
                editor.refresh_all_templates()
