"""
主窗口模块
实现应用程序的主界面，包括菜单栏、工具栏、状态栏等
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QToolBar, QStatusBar, QTreeWidget, QTreeWidgetItem,
    QFileDialog, QMessageBox, QTabWidget, QLabel, QPushButton,
    QDockWidget, QTextEdit, QComboBox, QSpinBox, QCheckBox,
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QInputDialog,
    QAbstractItemView, QMenu, QProgressDialog,QApplication
)
from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher, QItemSelectionModel
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

from .config_manager import ConfigManager
from .project_manager import ProjectManager
from .dbc_parser import DBCParser
from .case_editor import ModularCaseEditor
from .dsl_text_editor import DSLTextEditor
from .dialogs import (
    NewProjectDialog, DBCMappingDialog, SystemVariableDialog,
    AIQuestionDialog, OSSConfigDialog, DBCConverterDialog, AIConfigDialog,
    ReadOnlyTextEdit, CANoeProjectDialog, SimulinkFileDialog, SceneMappingDialog
)
from .ai_tool import ChatAIDialog, FloatingButton, APIConfigDialog


class ProjectTreeWidget(QTreeWidget):
    """自定义项目树控件，支持键盘快捷键"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None
        self.copy_shortcut = None
        self.paste_shortcut = None
        self._last_click_modifiers = Qt.KeyboardModifier(0)

    def mouseReleaseEvent(self, event):
        """捕获鼠标释放时的修饰键状态，供 itemClicked 处理器使用"""
        self._last_click_modifiers = event.modifiers()
        super().mouseReleaseEvent(event)

    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.copy_shortcut.activated.connect(self.on_copy_shortcut)

        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self.paste_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.paste_shortcut.activated.connect(self.on_paste_shortcut)

    def on_copy_shortcut(self):
        """Ctrl+C 快捷键处理"""
        if not self.main_window:
            return
        selected_items = self.selectedItems()
        if not selected_items:
            return

        first_item = selected_items[0]
        item_data = first_item.data(0, Qt.ItemDataRole.UserRole)

        if item_data:
            item_type = item_data.get("type")
            if item_type == "automation_file":
                file_path = item_data.get("path", "")
                case_type = item_data.get("case_type", "py")
                self.main_window.copy_automation_file(file_path, case_type)
            elif item_type == "automation_directory":
                dir_path = item_data.get("path", "")
                case_type = item_data.get("case_type", "py")
                self.main_window.copy_automation_directory(dir_path, case_type)
            else:
                self.main_window.copy_dsl_items(selected_items)
        else:
            self.main_window.copy_dsl_items(selected_items)

    def on_paste_shortcut(self):
        """Ctrl+V 快捷键处理"""
        if not self.main_window or not self.main_window.clipboard:
            return
        current_item = self.currentItem()
        if not current_item:
            return

        item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        clipboard_type = self.main_window.clipboard.get("type")
        is_automation_clipboard = clipboard_type in ("automation_file", "automation_directory")

        if is_automation_clipboard:
            case_type = self.main_window.clipboard.get("case_type", "py")
            target_directory = self._resolve_automation_paste_target(current_item, item_data, case_type)
            if target_directory is not None:
                self.main_window.paste_automation_item(target_directory, case_type)
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
        self.statusbar.addWidget(self.status_label)
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
        dialog = NewProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project_path = dialog.get_project_path()
            project_name = dialog.get_project_name()
            if self.project_manager.create_project(project_path, project_name):
                self.config_manager.add_recent_project(str(self.project_manager.get_project_path()))
                self.update_recent_menu()
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
        if self.project_manager.is_project_open():
            self._clear_file_watcher()

        if self.project_manager.open_project(project_path):
            self.config_manager.add_recent_project(project_path)
            self.update_recent_menu()
            self.load_project_config()
            self._cleanup_missing_file_references()
            self._setup_file_watcher()
            self.update_project_tree()
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

        mapping = self.project_manager.get_can_channel_mapping()
        self.dbc_parser.set_can_channel_mapping(mapping)
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

    # ==================== 文件监视器 ====================

    def _setup_file_watcher(self) -> None:
        """设置文件监视器，监听项目目录变化"""
        dirs = self._collect_watch_dirs()
        if dirs:
            self.file_watcher.addPaths(dirs)
            
    def _collect_watch_dirs(self) -> List[str]:
        """收集所有需要监视的目录（根目录 + 递归子目录）"""
        if not self.project_manager.is_project_open():
            return []
        project_path = self.project_manager.current_project_path
        if not project_path:
            return []
 
        watch_root_dirs = [
            str(project_path),
            str(project_path / "CANoe" / "dbc_file"),
            str(project_path / "CANoe" / "env_dbc"),
            str(project_path / "CANoe" / "system_variable"),
            str(project_path / "dsl_case"),
            str(project_path / "Scene"),
            str(project_path / "TestRequirements"),
            str(project_path / "automation_case"),
            str(project_path / "automation_case" / "py_cases"),
            str(project_path / "automation_case" / "json_cases"),
        ]
 
        all_dirs = []
        for root_dir in watch_root_dirs:
            root_path = Path(root_dir)
            if root_path.exists():
                all_dirs.append(root_dir)
                for item in root_path.rglob("*"):
                    if item.is_dir():
                        all_dirs.append(str(item))
        return all_dirs
    
    def _sync_file_watcher(self) -> None:
        """增量同步文件监视器：添加新出现的子目录，移除已删除的目录"""
        desired = set(self._collect_watch_dirs())
        current = set(self.file_watcher.directories())
 
        to_remove = current - desired
        to_add = desired - current
 
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

    def on_directory_changed(self, path: str) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(300)

    def on_file_changed(self, path: str) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(300)

    def _do_refresh_project_tree(self) -> None:
        """执行项目树刷新"""
        if self.project_manager.is_project_open():
            self._cleanup_missing_file_references()
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

        # 清理纯字符串列表类型
        for key in ("dbc_files", "env_dbc_files", "system_variable_files"):
            items = cfg.get(key, [])
            valid = []
            for path_str in items:
                if _resolve_and_check(path_str):
                    valid.append(path_str)
                else:
                    config_changed = True
            cfg[key] = valid

        if config_changed:
            self.project_manager.save_project()

    # ==================== 项目树 ====================

    def update_project_tree(self) -> None:
        """更新项目树"""
        saved_expanded = self._save_expanded_state()
        saved_current_data = None
        current_item = self.project_tree.currentItem()
        if current_item:
            saved_current_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        saved_selections = self._save_selected_items()

        self.project_tree.clear()

        if not self.project_manager.is_project_open():
            return

        self.project_manager.sync_dsl_cases()
        self.project_manager.sync_automation_cases()

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

        if saved_expanded:
            self._restore_expanded_state(saved_expanded)
        self._restore_selected_items(saved_selections)
        if saved_current_data:
            self._restore_tree_item_by_data(saved_current_data)

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

    def _restore_tree_item_by_data(self, item_data: Dict[str, Any]) -> None:
        """根据节点的 UserRole 数据恢复树当前项（不清除已有选中状态）"""
        root = self.project_tree.invisibleRootItem()
        found = self._find_tree_item_by_data(root, item_data)
        if found:
            self.project_tree.setCurrentItem(found, 0, QItemSelectionModel.SelectionFlag.Current)
            self.project_tree.scrollToItem(found)

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
            or (item_data and item_data.get("type") in ("directory", "automation_directory"))
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

        if item_data and item_data.get("type") in ("directory", "automation_directory"):
            item.setExpanded(not item.isExpanded())
            return

        if item.childCount() > 0 and not (item_data and item_data.get("type") in ("file", "automation_file")):
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

        if parent_text == "DSL Cases":
            case_name = file_name[:-4] if file_name.endswith('.dsl') else file_name
            self.open_case_text_editor(case_name)
        elif parent_text == "DBC文件":
            self.open_file_viewer(file_name, "CANoe/dbc_file")
        elif parent_text == "环境变量DBC文件":
            self.open_file_viewer(file_name, "CANoe/env_dbc")
        elif parent_text == "系统变量文件":
            self.open_file_viewer(file_name, "CANoe/system_variable")

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
        # 多选批量操作
        if has_multiple_selection:
            all_dsl_items = all(
                (d := si.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") in ("file", "directory")
                for si in selected_items
            )
            all_automation_items = all(
                (d := si.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") in ("automation_file", "automation_directory")
                for si in selected_items
            )
            if all_dsl_items:
                menu.addAction("复制").triggered.connect(lambda: self.copy_dsl_items(selected_items))
                menu.addAction("删除").triggered.connect(lambda: self.delete_dsl_items(selected_items))
                menu.exec(self.project_tree.mapToGlobal(position))
                return
            if all_automation_items:
                menu.addAction("删除").triggered.connect(lambda: self.delete_automation_items(selected_items))
                menu.exec(self.project_tree.mapToGlobal(position))
                return

        if item_text == "DSL Cases":
            menu.addAction("新建Case").triggered.connect(self.new_case)
            menu.addAction("添加目录").triggered.connect(lambda: self.add_dsl_directory(""))
            menu.addSeparator()
            menu.addAction("全部转换为 py/json").triggered.connect(lambda: self.convert_dsl_to_automation("", True))

        elif item_data and item_data.get("type") == "directory":
            directory_path = item_data.get("path", "")
            menu.addAction("添加目录").triggered.connect(lambda: self.add_dsl_directory(directory_path))
            menu.addAction("新建Case").triggered.connect(lambda: self.new_case_in_directory(directory_path))
            menu.addSeparator()
            menu.addAction("批量转换为 py/json").triggered.connect(lambda: self.convert_dsl_to_automation(directory_path, False))
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(lambda: self.copy_dsl_directory(directory_path))
            paste_action = menu.addAction("粘贴")
            paste_action.triggered.connect(lambda: self.paste_dsl_item(directory_path))
            paste_action.setEnabled(self.clipboard is not None)
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(lambda: self.rename_dsl_directory(directory_path))
            menu.addAction("删除目录").triggered.connect(lambda: self.delete_dsl_directory(directory_path))

        elif item_data and item_data.get("type") == "file":
            file_path = item_data.get("path", "")
            if file_path.endswith('.dsl'):
                case_name = PurePosixPath(file_path).stem
                directory = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
                menu.addAction("编辑").triggered.connect(lambda: self.open_case_modular_editor_with_directory(case_name, directory))
                menu.addSeparator()
                menu.addAction("转换为 py/json").triggered.connect(lambda: self.convert_single_dsl_to_automation(case_name, directory))
                menu.addSeparator()
                menu.addAction("复制").triggered.connect(lambda: self.copy_dsl_case(case_name, directory))
                paste_action = menu.addAction("粘贴")
                paste_action.triggered.connect(lambda: self.paste_dsl_item(directory))
                paste_action.setEnabled(self.clipboard is not None)
                menu.addSeparator()
                menu.addAction("重命名").triggered.connect(lambda: self.rename_dsl_case(case_name, directory))
                menu.addAction("删除").triggered.connect(lambda: self.delete_case_with_directory(case_name, directory))

        elif tree_parent and tree_parent.text(0) == "DSL Cases":
            menu.addAction("编辑").triggered.connect(lambda: self.open_case_modular_editor(item_text))
            menu.addAction("删除").triggered.connect(lambda: self.delete_case(item_text))

        elif item_text == "DBC文件":
            menu.addAction("添加文件").triggered.connect(self.add_dbc_file)
        elif tree_parent and tree_parent.text(0) == "DBC文件":
            menu.addAction("删除").triggered.connect(lambda: self.delete_dbc_file(item.text(0)))

        elif item_text == "环境变量DBC文件":
            menu.addAction("添加文件").triggered.connect(self.add_env_dbc_file)
        elif tree_parent and tree_parent.text(0) == "环境变量DBC文件":
            menu.addAction("删除").triggered.connect(lambda: self.delete_env_dbc_file(item.text(0)))

        elif item_text == "系统变量文件":
            menu.addAction("添加文件").triggered.connect(self.add_system_variable_file)
        elif tree_parent and tree_parent.text(0) == "系统变量文件":
            menu.addAction("删除").triggered.connect(lambda: self.delete_system_variable_file(item.text(0)))

        elif item_text == "Scene":
            menu.addAction("添加场景映射表").triggered.connect(self.add_scene_mapping)
        elif tree_parent and tree_parent.text(0) == "Scene":
            mapping_name = item.text(0)
            menu.addAction("查看").triggered.connect(lambda: self.open_scene_mapping(mapping_name))
            menu.addAction("删除").triggered.connect(lambda: self.delete_scene_mapping(mapping_name))

        elif item_text == "Test Requirements":
            menu.addAction("添加测试需求文档").triggered.connect(self.add_test_requirement)
        elif tree_parent and tree_parent.text(0) == "Test Requirements":
            doc_name = item.text(0)
            menu.addAction("查看").triggered.connect(lambda: self.open_test_requirement(doc_name))
            menu.addAction("删除").triggered.connect(lambda: self.delete_test_requirement(doc_name))

        elif item_text == "Automation Cases":
            pass  # 空菜单

        elif item_text == "py_cases":
            menu.addAction("新增子目录").triggered.connect(lambda: self.add_automation_directory("py_cases"))
        elif item_text == "json_cases":
            menu.addAction("新增子目录").triggered.connect(lambda: self.add_automation_directory("json_cases"))

        elif item_data and item_data.get("type") == "automation_directory":
            dir_path = item_data.get("path", "")
            case_type = item_data.get("case_type", "py")
            parent_key = f"{case_type}_cases/{dir_path}" if dir_path else f"{case_type}_cases"
            menu.addAction("新增子目录").triggered.connect(lambda: self.add_automation_directory(parent_key))
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(lambda: self.copy_automation_directory(dir_path, case_type))
            menu.addAction("粘贴").triggered.connect(lambda: self.paste_automation_item(dir_path, case_type))
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(lambda: self.rename_automation_directory(dir_path, case_type))
            menu.addAction("删除").triggered.connect(lambda: self.delete_automation_directory(dir_path, case_type))

        elif item_data and item_data.get("type") == "automation_file":
            file_path = item_data.get("path", "")
            case_type = item_data.get("case_type", "py")
            directory = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
            menu.addAction("打开").triggered.connect(lambda: self.open_automation_file(file_path, case_type))
            menu.addSeparator()
            menu.addAction("复制").triggered.connect(lambda: self.copy_automation_file(file_path, case_type))
            menu.addAction("粘贴").triggered.connect(lambda: self.paste_automation_item(directory, case_type))
            menu.addSeparator()
            menu.addAction("重命名").triggered.connect(lambda: self.rename_automation_file(file_path, case_type))
            menu.addAction("删除").triggered.connect(lambda: self.delete_automation_file(file_path, case_type))

        menu.exec(self.project_tree.mapToGlobal(position))

    # ==================== 文件添加/删除 (CANoe) ====================

    def add_dbc_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择DBC文件", "", "DBC文件 (*.dbc);;所有文件 (*.*)")
        if file_path:
            if self.project_manager.add_dbc_file(file_path):
                self.dbc_parser.load_dbc_file(file_path, "normal")
                self.update_project_tree()
                self.update_all_editor_completions()
                self.update_status(f"DBC文件 '{Path(file_path).name}' 添加成功")
            else:
                QMessageBox.critical(self, "错误", "添加DBC文件失败")

    def add_env_dbc_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择环境变量DBC文件", "", "DBC文件 (*.dbc);;所有文件 (*.*)")
        if file_path:
            if self.project_manager.add_env_dbc_file(file_path):
                self.dbc_parser.load_dbc_file(file_path, "env")
                self.update_project_tree()
                self.update_all_editor_completions()
                self.update_status(f"环境变量DBC文件 '{Path(file_path).name}' 添加成功")
            else:
                QMessageBox.critical(self, "错误", "添加环境变量DBC文件失败")

    def add_system_variable_file(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择系统变量文件", "", "所有文件 (*.*)")
        if file_path:
            if self.project_manager.add_system_variable_file(file_path):
                self.dbc_parser.load_system_variables(file_path)
                self.update_project_tree()
                self.update_all_editor_completions()
                self.update_status(f"系统变量文件 '{Path(file_path).name}' 添加成功")
            else:
                QMessageBox.critical(self, "错误", "添加系统变量文件失败")

    def config_can_mapping(self) -> None:
        if not self.project_manager.is_project_open():
            QMessageBox.warning(self, "警告", "请先打开或创建项目")
            return
        dialog = DBCMappingDialog(self.project_manager.get_dbc_files(),
                                  self.project_manager.get_can_channel_mapping(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mapping = dialog.get_mapping()
            if self.project_manager.set_can_channel_mapping(mapping):
                self.dbc_parser.set_can_channel_mapping(mapping)
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
        dialog = SimulinkFileDialog(current_files, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.get_files()
            for file_info in files:
                self.project_manager.add_simulink_file(file_info["path"], file_info["type"], copy_to_project=False)
            self.update_project_tree()
            self.update_status("Simulink工程文件配置成功")

    def delete_dbc_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除DBC文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.project_manager.remove_dbc_file(file_name):
                self.dbc_parser.unload_dbc_file(file_name)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"DBC文件 '{file_name}' 已删除")
            else:
                QMessageBox.critical(self, "错误", f"删除DBC文件 '{file_name}' 失败")

    def delete_env_dbc_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除环境变量DBC文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.project_manager.remove_env_dbc_file(file_name):
                self.dbc_parser.unload_dbc_file(file_name)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"环境变量DBC文件 '{file_name}' 已删除")
            else:
                QMessageBox.critical(self, "错误", f"删除环境变量DBC文件 '{file_name}' 失败")

    def delete_system_variable_file(self, file_name: str) -> None:
        if not self.project_manager.is_project_open():
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除系统变量文件 '{file_name}' 吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.project_manager.remove_system_variable_file(file_name):
                self.dbc_parser.remove_system_variables(file_name)
                self.update_all_editor_completions()
                self.update_project_tree()
                self.update_status(f"系统变量文件 '{file_name}' 已删除")
            else:
                QMessageBox.critical(self, "错误", f"删除系统变量文件 '{file_name}' 失败")

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

        self.update_project_tree()
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

        self.update_project_tree()
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
        reply = QMessageBox.question(self, "确认删除", f"确定要删除目录 '{directory}' 及其所有内容吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
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

        if self.project_manager.delete_dsl_directory(directory):
            self.update_project_tree()
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

    def delete_dsl_items(self, items: List[QTreeWidgetItem]) -> None:
        """批量删除 DSL 文件和目录"""
        if not items:
            return
        file_count = sum(1 for it in items if (d := it.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") == "file")
        dir_count = sum(1 for it in items if (d := it.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") == "directory")

        message = "确定要删除以下项目吗？\n\n"
        if file_count > 0:
            message += f"文件: {file_count} 个\n"
        if dir_count > 0:
            message += f"目录: {dir_count} 个\n"

        reply = QMessageBox.question(self, "确认删除", message,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        for item in items:
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path.endswith('.dsl'):
                    cn = Path(file_path).stem
                    d = str(Path(file_path).parent) if Path(file_path).parent != Path(".") else ""
                    if self.project_manager.delete_dsl_case(cn, d):
                        fk = f"{d}/{cn}" if d else cn
                        self.close_case_tab(fk)
                        success_count += 1
            elif item_data and item_data.get("type") == "directory":
                d = item_data.get("path", "")
                if self.project_manager.delete_dsl_directory(d):
                    self.close_directory_tabs(d)
                    success_count += 1

        self.update_project_tree()
        self.update_status(f"已删除 {success_count} 个项目")

    # ==================== DSL 复制/粘贴 ====================

    def copy_dsl_case(self, case_name: str, directory: str) -> None:
        self.clipboard = {"type": "items", "items": [{"type": "file", "case_name": case_name, "directory": directory}]}
        self.update_status(f"已复制Case '{case_name}.dsl'")

    def copy_dsl_directory(self, directory: str) -> None:
        self.clipboard = {"type": "items", "items": [{"type": "directory", "directory": directory}]}
        self.update_status(f"已复制目录 '{directory}'")

    def copy_dsl_items(self, items: List[QTreeWidgetItem]) -> None:
        clipboard_items = []
        for item in items:
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "file":
                file_path = item_data.get("path", "")
                if file_path.endswith('.dsl'):
                    cn = PurePosixPath(file_path).stem
                    d = str(PurePosixPath(file_path).parent) if str(PurePosixPath(file_path).parent) != "." else ""
                    clipboard_items.append({"type": "file", "case_name": cn, "directory": d})
            elif item_data and item_data.get("type") == "directory":
                clipboard_items.append({"type": "directory", "directory": item_data.get("path", "")})
        if clipboard_items:
            self.clipboard = {"type": "items", "items": clipboard_items}
            self.update_status(f"已复制 {len(clipboard_items)} 个项目")

    def paste_dsl_item(self, target_directory: str) -> None:
        if not self.clipboard:
            return
        cb_type = self.clipboard.get("type")
        if cb_type == "file":
            self._paste_single_file(self.clipboard["case_name"], self.clipboard["directory"], target_directory)
        elif cb_type == "directory":
            src = self.clipboard["directory"]
            dn = src.split("/")[-1] if "/" in src else src
            self._paste_single_directory(src, dn, target_directory)
        elif cb_type == "items":
            for item in self.clipboard.get("items", []):
                if item["type"] == "file":
                    self._paste_single_file(item["case_name"], item["directory"], target_directory)
                elif item["type"] == "directory":
                    src = item["directory"]
                    dn = src.split("/")[-1] if "/" in src else src
                    self._paste_single_directory(src, dn, target_directory)

    def _paste_single_file(self, old_case_name: str, source_directory: str, target_directory: str) -> None:
        """粘贴单个 DSL 文件"""
        source_relative = f"dsl_case/{source_directory}/{old_case_name}.dsl" if source_directory else f"dsl_case/{old_case_name}.dsl"
        source_file = self.project_manager.get_full_path(source_relative)
        if not source_file or not source_file.exists():
            QMessageBox.critical(self, "错误", f"源文件不存在: {old_case_name}.dsl")
            return

        target_dir = self.project_manager.get_full_path(f"dsl_case/{target_directory}") if target_directory else self.project_manager.get_full_path("dsl_case")
        if not target_dir:
            QMessageBox.critical(self, "错误", "目标目录无效")
            return
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
            "name": new_name, "file": relative_path,
            "directory": target_directory, "created_time": datetime.now().isoformat()
        })
        self.project_manager.save_project()
        self.update_project_tree()
        self.open_case_modular_editor_with_directory(new_name, target_directory)

    def _paste_single_directory(self, source_directory: str, dir_name: str, target_directory: str) -> None:
        """粘贴单个 DSL 目录"""
        source_dir = self.project_manager.get_full_path(f"dsl_case/{source_directory}")
        if not source_dir or not source_dir.exists():
            QMessageBox.critical(self, "错误", f"源目录不存在: {source_directory}")
            return

        target_dir = self.project_manager.get_full_path(f"dsl_case/{target_directory}") if target_directory else self.project_manager.get_full_path("dsl_case")
        if not target_dir:
            QMessageBox.critical(self, "错误", "目标目录无效")
            return
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
        self.update_project_tree()
        QTimer.singleShot(50, lambda: self._highlight_directory_node(new_dir_name, target_directory))
        QTimer.singleShot(50, lambda: self.project_tree.setFocus())
        self.update_status(f"目录 '{new_dir_name}' 已粘贴")

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
        for dbc_path, channel in self.dbc_parser.can_channel_mapping.items():
            channels.add(f"CAN {channel}")
        for channel in sorted(channels):
            completions.append(f"sig::{channel}::")
            completions.append(f"env::{channel}::")

        for dbc_path, db in self.dbc_parser.dbc_files.items():
            channel = self.dbc_parser.get_can_channel_for_dbc(dbc_path)
            if channel is None:
                continue
            for msg in db.messages:
                sig_prefix = f"sig::CAN {channel}::{msg.name}::"
                env_prefix = f"env::CAN {channel}::{msg.name}::"
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
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            for i in range(self.editor_tabs.count()):
                if self.editor_tabs.tabText(i) == file_name:
                    self.editor_tabs.setCurrentIndex(i)
                    return
            editor = DSLTextEditor()
            editor.set_content(content)
            if file_type in ("dbc_file", "env_dbc", "system_variable"):
                editor.setReadOnly(True)
            tab = self.editor_tabs.addTab(editor, file_name)
            self.editor_tabs.setCurrentIndex(tab)
            self.update_status(f"打开文件 '{file_name}' (只读模式)")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {e}")

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
        dialog = DBCConverterDialog(self)
        dialog.exec()

    def open_oss_config(self) -> None:
        dialog = OSSConfigDialog(self.config_manager, self)
        dialog.exec()

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
            "delete_test_requirement": self._undo_delete_test_requirement,
            "delete_scene_mapping": self._undo_delete_scene_mapping,
            "delete_automation_file": self._undo_delete_automation_file,
        }.get(operation)
        if handler:
            handler(undo_info)

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
        dialog = SceneMappingDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mapping_name = dialog.get_mapping_name()
            file_path = dialog.get_mapping_file_path()
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

        progress = QProgressDialog("正在转换...", "取消", 0, len(files), self)
        progress.setWindowTitle("转换进度")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        success_count = skip_count = error_count = 0

        for i, (case_name, directory) in enumerate(files):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"正在转换: {case_name}")
            try:
                dsl_content = self.project_manager.load_dsl_case(case_name, directory)
                if dsl_content is None:
                    error_count += 1
                    continue
                if convert_py:
                    r = self._convert_to_py(case_name, directory, dsl_content, options)
                    if r == "success":
                        success_count += 1
                    elif r == "skip":
                        skip_count += 1
                    else:
                        error_count += 1
                if convert_json:
                    r = self._convert_to_json(case_name, directory, dsl_content, options)
                    if not convert_py:
                        if r == "success":
                            success_count += 1
                        elif r == "skip":
                            skip_count += 1
                        else:
                            error_count += 1
            except Exception as e:
                print(f"转换失败: {case_name}, 错误: {e}")
                error_count += 1

        progress.setValue(len(files))
        self.update_project_tree()
        QMessageBox.information(self, "转换完成", f"转换完成！\n成功: {success_count}\n跳过: {skip_count}\n失败: {error_count}")

    def _convert_to_py(self, case_name: str, directory: str, dsl_content: str, options: Dict) -> str:
        target_dir = self.project_manager.current_project_path / "automation_case" / "py_cases"
        if directory:
            target_dir = target_dir / directory
        target_path = target_dir / f"{case_name}.py"

        if target_path.exists():
            action = options.get("exist_action", "ask")
            if action == "skip":
                return "skip"
            elif action == "rename":
                new_name, ok = QInputDialog.getText(self, "重命名", f"文件 {case_name}.py 已存在，请输入新名称:", text=case_name)
                if not ok or not new_name:
                    return "skip"
                target_path = target_dir / f"{new_name}.py"

        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            from .convert_2_pycase import parse_dsl_case, convert_case_to_python_module
            dsl = parse_dsl_case(dsl_content, fallback_name=case_name)
            py_content = convert_case_to_python_module(dsl)
        except Exception as e:
            print(f"转换失败: {e}")
            return "error"

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(py_content)
        actual_name = target_path.stem
        dir_path = str(target_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / "py_cases"))
        directory = dir_path if dir_path != "." else ""
        self.project_manager.add_automation_case(actual_name, "py", directory)
        return "success"

    def _convert_to_json(self, case_name: str, directory: str, dsl_content: str, options: Dict) -> str:
        target_dir = self.project_manager.current_project_path / "automation_case" / "json_cases"
        if directory:
            target_dir = target_dir / directory
        target_path = target_dir / f"{case_name}.json"

        if target_path.exists():
            action = options.get("exist_action", "ask")
            if action == "skip":
                return "skip"
            elif action == "rename":
                new_name, ok = QInputDialog.getText(self, "重命名", f"文件 {case_name}.json 已存在，请输入新名称:", text=case_name)
                if not ok or not new_name:
                    return "skip"
                target_path = target_dir / f"{new_name}.json"

        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            import tempfile
            from .json_case_conversion import convert_dsl_to_json
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dsl', delete=False, encoding='utf-8') as tmp:
                tmp.write(dsl_content)
                tmp_path = tmp.name
            try:
                success = convert_dsl_to_json(input_path=tmp_path, output_path=str(target_path))
                if not success:
                    return "error"
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            print(f"JSON 转换失败: {e}")
            return "error"
        actual_name = target_path.stem
        dir_path = str(target_path.parent.relative_to(self.project_manager.current_project_path / "automation_case" / "json_cases"))
        directory = dir_path if dir_path != "." else ""
        self.project_manager.add_automation_case(actual_name, "json", directory)
        return "success"

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
            
    def delete_automation_items(self, items: List[QTreeWidgetItem]) -> None:
        """批量删除 Automation Cases 文件和目录"""
        if not items:
            return

        file_count = sum(1 for it in items if (d := it.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") == "automation_file")
        dir_count = sum(1 for it in items if (d := it.data(0, Qt.ItemDataRole.UserRole)) and d.get("type") == "automation_directory")

        message = "确定要删除以下项目吗？\n\n"
        if file_count > 0:
            message += f"文件: {file_count} 个\n"
        if dir_count > 0:
            message += f"目录: {dir_count} 个\n"

        reply = QMessageBox.question(self, "确认删除", message,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        for item in items:
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if not item_data:
                continue
            item_type = item_data.get("type")
            case_type = item_data.get("case_type", "py")
            base = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"

            try:
                if item_type == "automation_file":
                    fp = base / item_data.get("path", "")
                    if fp.exists():
                        fp.unlink()
                        file_key = f"automation:{case_type}:{item_data.get('path', '')}"
                        self.close_case_tab(file_key)
                        dir_path = str(fp.parent.relative_to(base))
                        directory = dir_path if dir_path != "." else ""
                        self.project_manager.remove_automation_case(fp.stem, case_type, directory)
                        success_count += 1
                elif item_type == "automation_directory":
                    dp = base / item_data.get("path", "")
                    if dp.exists():
                        dir_key_prefix = f"automation:{case_type}:{item_data.get('path', '')}"
                        self.close_automation_directory_tabs(dir_key_prefix)
                        shutil.rmtree(dp)
                        success_count += 1
            except Exception:
                pass

        self.project_manager.sync_automation_cases()
        self.update_project_tree()
        self.update_status(f"已删除 {success_count} 个项目")

    def delete_automation_directory(self, dir_path: str, case_type: str) -> None:
        reply = QMessageBox.question(self, "确认删除", f"确定要删除目录 '{dir_path}' 及其所有内容吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            full_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases" / dir_path
            try:
                dir_key_prefix = f"automation:{case_type}:{dir_path}"
                self.close_automation_directory_tabs(dir_key_prefix)
                shutil.rmtree(full_path)
                self.project_manager.sync_automation_cases()
                self.update_project_tree()
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

    def paste_automation_item(self, target_dir: str, case_type: str) -> None:
        if not self.clipboard:
            return
        try:
            base_path = self.project_manager.current_project_path / "automation_case" / f"{case_type}_cases"
            target_path = base_path / target_dir if target_dir else base_path
 
            new_file_path = None
            new_dir_path = None
 
            if self.clipboard["type"] == "automation_file":
                src_path = base_path / self.clipboard["file_path"]
                suffix = src_path.suffix
                new_stem = f"{src_path.stem}_copy"
                dst_path = target_path / f"{new_stem}{suffix}"
                while dst_path.exists():
                    new_stem = f"{new_stem}_copy"
                    dst_path = target_path / f"{new_stem}{suffix}"
                shutil.copy2(src_path, dst_path)
                dst_name = dst_path.name
                new_file_path = f"{target_dir}/{dst_name}" if target_dir else dst_name
 
            elif self.clipboard["type"] == "automation_directory":
                src_path = base_path / self.clipboard["dir_path"]
                new_dir_name = f"{src_path.name}_copy"
                dst_path = target_path / new_dir_name
                while dst_path.exists():
                    new_dir_name = f"{new_dir_name}_copy"
                    dst_path = target_path / new_dir_name
                shutil.copytree(src_path, dst_path)
                new_dir_path = f"{target_dir}/{new_dir_name}" if target_dir else new_dir_name

            self.project_manager.sync_automation_cases()
            self.update_project_tree()
            if new_file_path:
                QTimer.singleShot(50, lambda: self._highlight_automation_node(new_file_path, case_type))
            elif new_dir_path:
                QTimer.singleShot(50, lambda: self._highlight_automation_directory_node(new_dir_path, case_type))
            QTimer.singleShot(50, lambda: self.project_tree.setFocus())
            self.update_status("粘贴成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"粘贴失败: {e}")
