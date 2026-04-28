try:
    from .case_editor_1 import *
    from .case_editor_1 import (
        _align_form_layout,
        _fix_label_for_field,
        _setup_groupbox_style,
        _setup_scroll,
    )
except ImportError:
    from case_editor_1 import *
    from case_editor_1 import (
        _align_form_layout,
        _fix_label_for_field,
        _setup_groupbox_style,
        _setup_scroll,
    )

class StepWidget(QWidget):
    add_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    template_selected = pyqtSignal(object, dict)

    def __init__(self, step_id: str, step_type: str = "SET", parent=None):
        super().__init__(parent)
        self.step_id = step_id
        self.step_type = step_type
        self._build_ui()

    def _build_ui(self) -> None:
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(FORM_HSPACING)
        self.id_label = QLabel(f"{self.step_id}:", self)
        self.id_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.id_label.setStyleSheet("color: #569CD6;")
        self.id_label.setFixedWidth(FORM_LABEL_WIDTH)
        self.id_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.content_edit = ReadOnlyLineEdit(self)
        self.content_edit.setMinimumWidth(480)
        self.content_edit.setPlaceholderText("set sys::FunctionSwitch::CSW_Enable_S=0x1 wait 500ms then check C1" if self.step_type == "SET" else "check sig::CAN 1::ADC_0x29C::CSW_Stats_S==3 timeout 1000ms async false")
        self.content_edit.setStyleSheet("QLineEdit { border: 1px solid #cccccc; border-radius: 3px; padding: 5px; background-color: #f7f7f7; }")
        self.template_btn = QPushButton("选择模板", self)
        self.template_btn.setFixedWidth(75)
        self.template_menu = QMenu(self.template_btn)
        self.template_btn.clicked.connect(self._show_template_menu)
        self.btn_edit = QPushButton("编辑", self)
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self))
        self.btn_add = QPushButton("+", self)
        self.btn_add.clicked.connect(lambda: self.add_requested.emit(self))
        self.btn_del = QPushButton("-", self)
        self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self))
        for btn in (self.btn_edit, self.btn_add, self.btn_del):
            btn.setFixedWidth(68)
        row_layout.addWidget(self.id_label)
        row_layout.addWidget(self.content_edit, 1)
        row_layout.addWidget(self.template_btn)
        row_layout.addWidget(self.btn_edit)
        row_layout.addWidget(self.btn_add)
        row_layout.addWidget(self.btn_del)

    def _show_template_menu(self) -> None:
        self.template_menu.exec(self.template_btn.mapToGlobal(self.template_btn.rect().bottomLeft()))

    def _on_template_selected(self, template_data: Dict[str, Any]) -> None:
        self.template_selected.emit(self, template_data)

    def update_templates(self, templates: List[Dict[str, Any]]) -> None:
        self.template_menu.clear()
        for template in templates:
            action = self.template_menu.addAction(template.get("comment", ""))
            action.triggered.connect(lambda checked=False, t=template: self._on_template_selected(t))

    def set_step_id(self, new_id: str) -> None:
        self.step_id = new_id
        self.id_label.setText(f"{new_id}:")

    def get_step_content(self) -> str:
        return self.content_edit.text().strip()

    def set_step_content(self, content: Any) -> None:
        self.content_edit.setText("" if content is None or content is False else str(content))


class _BaseStepsWidget(QWidget):
    steps_changed = pyqtSignal()

    step_prefix = "S"
    step_type = "SET"

    def __init__(self, parent=None, dbc_parser=None, project_manager=None):
        super().__init__(parent)
        self.steps: List[StepWidget] = []
        self.completions: List[str] = []
        self._dbc_parser = dbc_parser
        self._project_manager = project_manager
        self._build_ui()
        self.add_step(after_step=None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        group = QGroupBox(f"{self.step_type}模块", self)
        _setup_groupbox_style(group)
        group.setMinimumHeight(200)
        group_layout = QVBoxLayout(group)
        self.steps_scroll = QScrollArea(group)
        _setup_scroll(self.steps_scroll)
        self.steps_container = QWidget(self.steps_scroll)
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(6)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.steps_scroll.setWidget(self.steps_container)
        group_layout.addWidget(self.steps_scroll)
        layout.addWidget(group)

    def set_completions(self, completions: List[str]) -> None:
        self.completions = completions

    def _completions_by_kind(self) -> Dict[str, List[str]]:
        return {
            "sys": [c for c in self.completions if c.startswith("sys::")],
            "env": [c for c in self.completions if c.startswith("env::")],
            "sig": [c for c in self.completions if c.startswith("sig::")],
        }

    def _templates(self) -> List[Dict[str, Any]]:
        return []

    def add_step(self, content: Any = "", after_step: Optional[StepWidget] = None) -> None:
        step = StepWidget("?", self.step_type, self.steps_container)
        step.set_step_content(content)
        step.add_requested.connect(self._on_add_requested)
        step.delete_requested.connect(self._on_delete_requested)
        step.edit_requested.connect(self._on_edit_requested)
        step.template_selected.connect(self._on_template_selected)
        step.update_templates(self._templates())
        if after_step is not None and after_step in self.steps:
            self.steps.insert(self.steps.index(after_step) + 1, step)
        else:
            self.steps.append(step)
        self._rebuild_layout()
        self._renumber_steps()
        self.steps_changed.emit()

    def _on_add_requested(self, step: StepWidget) -> None:
        self.add_step(after_step=step)

    def _on_delete_requested(self, step: StepWidget) -> None:
        self.remove_step(step)

    def _on_edit_requested(self, step: StepWidget) -> None:
        QMessageBox.information(self, "提示", "请在完整集成环境中使用弹窗编辑功能。")

    def _on_template_selected(self, step: StepWidget, template: Dict[str, Any]) -> None:
        signal_name = template.get("signal_name", "")
        signal_value = template.get("signal_value", "")
        comment = template.get("comment", "")
        if self.step_type == "SET":
            kind = "env" if signal_name.startswith("env::") else "sys"
            step.set_step_content(render_set_step(SetStepModel(signals=[SetSignalModel(kind=kind, name=signal_name, value=signal_value)], comment=comment)))
        else:
            kind = "sys" if signal_name.startswith("sys::") else "env" if signal_name.startswith("env::") else "sig"
            step.set_step_content(render_check_step(CheckStepModel(items=[CheckItemModel(kind=kind, name=signal_name, mode=template.get("value_mode", "single"), op=template.get("operator", "=="), single_value=signal_value)], comment=comment)))
        self.steps_changed.emit()

    def remove_step(self, step: StepWidget) -> None:
        if step not in self.steps:
            return
        if len(self.steps) <= 1:
            step.set_step_content("")
            self.steps_changed.emit()
            return
        self.steps.remove(step)
        self.steps_layout.removeWidget(step)
        step.setParent(None)
        step.deleteLater()
        self._rebuild_layout()
        self._renumber_steps()
        self.steps_changed.emit()

    def _rebuild_layout(self) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        for step in self.steps:
            self.steps_layout.addWidget(step)

    def _renumber_steps(self) -> None:
        for i, step in enumerate(self.steps, start=1):
            step.set_step_id(f"{self.step_prefix}{i}")

    def get_steps(self) -> List[Dict[str, str]]:
        return [{"id": step.step_id, "content": step.get_step_content()} for step in self.steps]

    def set_steps(self, steps: List[Dict[str, Any]]) -> None:
        for step in self.steps:
            self.steps_layout.removeWidget(step)
            step.setParent(None)
            step.deleteLater()
        self.steps.clear()
        for step_data in steps:
            self.add_step(content=step_data.get("content", ""), after_step=self.steps[-1] if self.steps else None)
        if not self.steps:
            self.add_step(after_step=None)

    def clear(self) -> None:
        self.set_steps([])

    def refresh_templates(self) -> None:
        templates = self._templates()
        for step in self.steps:
            step.update_templates(templates)


class SetModuleWidget(_BaseStepsWidget):
    step_prefix = "S"
    step_type = "SET"

    def _templates(self) -> List[Dict[str, Any]]:
        if not self._project_manager or not self._project_manager.is_project_open():
            return []
        return self._project_manager.project_config.get("automation", {}).get("set_template", {}).get("templates", [])

    def apply_check_id_mapping(self, mapping: Dict[str, str]) -> None:
        if not mapping:
            return
        pat = re.compile(r"(then\s+check\s+)(C\d+(?:\s*,\s*C\d+)*)", re.IGNORECASE)
        for step in self.steps:
            text = step.get_step_content()
            def repl(m: re.Match) -> str:
                ids = [x.strip() for x in m.group(2).split(",") if x.strip()]
                return m.group(1) + ",".join(mapping.get(x, x) for x in ids)
            new_text = pat.sub(repl, text)
            if new_text != text:
                step.set_step_content(new_text)


class CheckModuleWidget(_BaseStepsWidget):
    check_id_mapping_emitted = pyqtSignal(dict)
    step_prefix = "C"
    step_type = "CHECK"

    def _templates(self) -> List[Dict[str, Any]]:
        if not self._project_manager or not self._project_manager.is_project_open():
            return []
        return self._project_manager.project_config.get("automation", {}).get("check_template", {}).get("templates", [])

    def _renumber_steps(self) -> None:
        mapping: Dict[str, str] = {}
        for i, step in enumerate(self.steps, start=1):
            new_id = f"C{i}"
            if step.step_id not in ("?", new_id):
                mapping[step.step_id] = new_id
            step.set_step_id(new_id)
        if mapping:
            self.check_id_mapping_emitted.emit(mapping)


class CaseInfoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = QGroupBox("CASE信息", self)
        _setup_groupbox_style(group)
        form = QFormLayout(group)
        _align_form_layout(form)
        self.case_name_edit = QLineEdit(group)
        self.case_name_edit.setPlaceholderText("输入CASE名称，如：OrinN_MR25_CSW_027_001")
        self.case_id_edit = QLineEdit(group)
        self.case_id_edit.setPlaceholderText("输入CASE ID")
        form.addRow("CASE名称*:", self.case_name_edit)
        form.addRow("CASE ID:", self.case_id_edit)
        _fix_label_for_field(form, self.case_name_edit)
        _fix_label_for_field(form, self.case_id_edit)
        layout.addWidget(group)
        layout.addStretch()

    def get_case_info(self) -> Dict[str, str]:
        return {"name": self.case_name_edit.text().strip(), "id": self.case_id_edit.text().strip()}

    def set_case_info(self, name: str, case_id: str = "") -> None:
        self.case_name_edit.setText(name)
        self.case_id_edit.setText(case_id)

    def clear(self) -> None:
        self.case_name_edit.clear()
        self.case_id_edit.clear()


class MetaInfoWidget(QWidget):
    status_updated = pyqtSignal(str)
    preset_selection_changed = pyqtSignal()

    def __init__(self, parent=None, project_manager=None):
        super().__init__(parent)
        self.project_manager = project_manager
        self._selected_preset_signals: List[str] = []
        self._selected_preset_scene = ""
        self._selected_preset_scene_runtime = ""
        layout = QVBoxLayout(self)
        group = QGroupBox("META信息", self)
        _setup_groupbox_style(group)
        form = QFormLayout(group)
        _align_form_layout(form)
        self.test_point_edit = QLineEdit(group)
        self.priority_combo = QComboBox(group)
        self.priority_combo.addItems(["P0-高", "P1-中", "P2-低"])
        self.owner_edit = QLineEdit(group)
        self.scene_mapping_combo = QComboBox(group)
        self.scene_mapping_combo.addItem("请选择场景映射表")
        self.scene_name_combo = QComboBox(group)
        self.scene_name_combo.addItem("请选择场景名称")
        self.scenario_id_edit = QLineEdit(group)
        self.scenario_id_edit.setReadOnly(True)
        self.ai_analysis_checkbox = QCheckBox("启用AI分析", group)
        self.use_preset_checkbox = QCheckBox("启用预设", group)
        self.record_checkbox = QCheckBox("启用记录", group)
        for label, widget in (
            ("测试点*:", self.test_point_edit),
            ("优先级:", self.priority_combo),
            ("负责人:", self.owner_edit),
            ("场景映射表:", self.scene_mapping_combo),
            ("场景名称:", self.scene_name_combo),
            ("场景ID:", self.scenario_id_edit),
        ):
            form.addRow(label, widget)
            _fix_label_for_field(form, widget)
        form.addRow("", self.ai_analysis_checkbox)
        form.addRow("", self.use_preset_checkbox)
        form.addRow("", self.record_checkbox)
        layout.addWidget(group)
        layout.addStretch()

    @staticmethod
    def _normalize_combo_text(value: Any) -> str:
        s = str(value if value is not None else "").strip().rstrip(",").strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            s = s[1:-1].strip()
        return s

    def refresh_scene_mappings(self) -> None:
        pass

    def get_meta_info(self) -> Dict[str, Any]:
        return {
            "test_point": self.test_point_edit.text().strip(),
            "priority": self.priority_combo.currentText(),
            "owner": self.owner_edit.text().strip(),
            "scenario_id": self.scenario_id_edit.text().strip(),
            "scenario_name": "" if self.scene_name_combo.currentText() == "请选择场景名称" else self.scene_name_combo.currentText(),
            "scene_mapping": "" if self.scene_mapping_combo.currentText() == "请选择场景映射表" else self.scene_mapping_combo.currentText(),
            "ai_analysis": self.ai_analysis_checkbox.isChecked(),
            "use_preset": self.use_preset_checkbox.isChecked(),
            "preset_signals": "".join(self._selected_preset_signals),
            "preset_scene": self._selected_preset_scene,
            "preset_scene_runtime": self._selected_preset_scene_runtime,
            "record": self.record_checkbox.isChecked(),
        }

    def set_meta_info(self, meta_info: Dict[str, Any]) -> None:
        self.test_point_edit.setText(meta_info.get("test_point", ""))
        self.priority_combo.setCurrentText(meta_info.get("priority", "P1-中"))
        self.owner_edit.setText(meta_info.get("owner", ""))
        self.scenario_id_edit.setText(str(meta_info.get("scenario_id", "")).strip().rstrip(","))
        self.ai_analysis_checkbox.setChecked(bool(meta_info.get("ai_analysis", False)))
        self.use_preset_checkbox.setChecked(bool(meta_info.get("use_preset", False)))
        self.record_checkbox.setChecked(bool(meta_info.get("record", False)))
        preset_signals_str = meta_info.get("preset_signals", "")
        self._selected_preset_signals = re.findall(r"P\d+", preset_signals_str) if preset_signals_str else []
        self._selected_preset_scene = meta_info.get("preset_scene", "")
        self._selected_preset_scene_runtime = meta_info.get("preset_scene_runtime", "")

    def clear(self) -> None:
        self.test_point_edit.clear()
        self.priority_combo.setCurrentIndex(1)
        self.owner_edit.clear()
        self.scenario_id_edit.clear()
        self.ai_analysis_checkbox.setChecked(False)
        self.use_preset_checkbox.setChecked(False)
        self.record_checkbox.setChecked(False)


