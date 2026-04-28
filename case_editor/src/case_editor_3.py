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


class FlowchartNode(QGraphicsItem):
    def __init__(self, node_type: str, node_id: str, data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.node_type = node_type
        self.node_id = node_id
        self.data = data
        self.width = 80 if node_type in ("start", "end") else 120
        self.height = 80 if node_type in ("start", "end") else 60
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.text_item = QGraphicsTextItem(self)
        self.text_item.setPlainText({"start": "开始", "end": "结束", "set": "SET Signal", "check": "CHECK Signal"}.get(node_type, node_id))
        self.text_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        rect = self.text_item.boundingRect()
        self.text_item.setPos((self.width - rect.width()) / 2, (self.height - rect.height()) / 2)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = {"start": QColor("#4CAF50"), "end": QColor("#f44336"), "set": QColor("#2196F3"), "check": QColor("#FF9800")}
        painter.setPen(QPen(QColor("#333333"), 2))
        painter.setBrush(QBrush(colors.get(self.node_type, QColor("#999999"))))
        if self.node_type in ("start", "end"):
            painter.drawEllipse(0, 0, self.width, self.height)
        else:
            painter.drawRoundedRect(0, 0, self.width, self.height, 10, 10)


class FlowchartEdge(QGraphicsPathItem):
    def __init__(self, source_node: FlowchartNode, target_node: FlowchartNode, parent=None):
        super().__init__(parent)
        self.source_node = source_node
        self.target_node = target_node
        self.setZValue(-1)
        self.setPen(QPen(QColor("#666666"), 2))
        self._update_path()

    def _update_path(self) -> None:
        sp = self.source_node.pos()
        tp = self.target_node.pos()
        path = QPainterPath()
        source_bottom = QPointF(sp.x() + self.source_node.width / 2, sp.y() + self.source_node.height)
        target_top = QPointF(tp.x() + self.target_node.width / 2, tp.y())
        mid_y = (source_bottom.y() + target_top.y()) / 2
        path.moveTo(source_bottom)
        path.lineTo(source_bottom.x(), mid_y)
        path.lineTo(target_top.x(), mid_y)
        path.lineTo(target_top)
        self.setPath(path)


class _AsyncBoolDelegate(QStyledItemDelegate):
    def __init__(self, async_row_getter, parent=None):
        super().__init__(parent)
        self._async_row_getter = async_row_getter

    def createEditor(self, parent, option, index):
        if self._async_row_getter() == index.row() and index.column() == 1:
            combo = QComboBox(parent)
            combo.addItems(["false", "true"])
            combo.activated.connect(lambda _i, c=combo: self._commit_and_close(c))
            return combo
        return super().createEditor(parent, option, index)

    def _commit_and_close(self, editor: QComboBox):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)


class FlowchartViewDialog(QDialog):
    save_requested = pyqtSignal()

    def __init__(self, set_steps: List[Dict[str, Any]], check_steps: List[Dict[str, Any]], parent=None, editor=None, save_callback=None):
        super().__init__(parent)
