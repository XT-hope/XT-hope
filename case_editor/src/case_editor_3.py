try:
    from .case_editor_1 import *
    from .case_editor_1 import _setup_scroll
    from .case_editor_2 import *
except ImportError:
    from case_editor_1 import *
    from case_editor_1 import _setup_scroll
    from case_editor_2 import *

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
        self.setWindowTitle("查看流程配置")
        self.resize(1200, 800)
        self.set_steps = set_steps
        self.check_steps = check_steps
        self.editor = editor
        self.save_callback = save_callback
        layout = QHBoxLayout(self)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.view, 1)
        self._build_flowchart()

    def _build_flowchart(self):
        self.scene.clear()
        nodes = [FlowchartNode("start", "START", {})]
        nodes.extend(FlowchartNode("set", step.get("id", ""), step) for step in self.set_steps)
        nodes.extend(FlowchartNode("check", step.get("id", ""), step) for step in self.check_steps)
        nodes.append(FlowchartNode("end", "END", {}))
        y = 20
        for node in nodes:
            node.setPos(160, y)
            self.scene.addItem(node)
            y += 110
        for i in range(len(nodes) - 1):
            self.scene.addItem(FlowchartEdge(nodes[i], nodes[i + 1]))
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-80, -40, 100, 100))


class ModularCaseEditor(QWidget):
    content_changed = pyqtSignal()
    save_to_file_requested = pyqtSignal()
    status_updated = pyqtSignal(str)

    def __init__(self, parent=None, dbc_parser=None, project_manager=None):
        super().__init__(parent)
        self.completions: List[str] = []
        self._dbc_parser = dbc_parser
        self.project_manager = project_manager
        self._build_ui()
        self._wire_signals()

    @staticmethod
    def _encode_meta_value(value: Any) -> str:
        s = str(value if value is not None else "").strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            s = s[1:-1].strip()
        return s

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        _setup_scroll(scroll)
        container = QWidget(scroll)
        container_layout = QVBoxLayout(container)
        self.case_info_widget = CaseInfoWidget(container)
        self.meta_info_widget = MetaInfoWidget(container, project_manager=self.project_manager)
        self.set_module_widget = SetModuleWidget(container, dbc_parser=self._dbc_parser, project_manager=self.project_manager)
        self.check_module_widget = CheckModuleWidget(container, dbc_parser=self._dbc_parser, project_manager=self.project_manager)
        self.view_flowchart_btn = QPushButton("查看流程配置", container)
        self.view_flowchart_btn.clicked.connect(self._on_view_flowchart)
        for widget in (self.case_info_widget, self.meta_info_widget, self.set_module_widget, self.check_module_widget, self.view_flowchart_btn):
            container_layout.addWidget(widget)
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _wire_signals(self) -> None:
        self.check_module_widget.check_id_mapping_emitted.connect(self.set_module_widget.apply_check_id_mapping)
        for signal in (
            self.case_info_widget.case_name_edit.textChanged,
            self.case_info_widget.case_id_edit.textChanged,
            self.meta_info_widget.test_point_edit.textChanged,
            self.meta_info_widget.priority_combo.currentTextChanged,
            self.meta_info_widget.owner_edit.textChanged,
            self.meta_info_widget.scenario_id_edit.textChanged,
            self.meta_info_widget.scene_name_combo.currentTextChanged,
            self.meta_info_widget.scene_mapping_combo.currentTextChanged,
            self.meta_info_widget.ai_analysis_checkbox.toggled,
            self.meta_info_widget.use_preset_checkbox.toggled,
            self.meta_info_widget.record_checkbox.toggled,
            self.set_module_widget.steps_changed,
            self.check_module_widget.steps_changed,
        ):
            signal.connect(self._emit_content_changed)

    def _emit_content_changed(self, *_args) -> None:
        self.content_changed.emit()

    def refresh_scene_mappings(self) -> None:
        self.meta_info_widget.refresh_scene_mappings()

    def refresh_all_templates(self) -> None:
        self.set_module_widget.refresh_templates()
        self.check_module_widget.refresh_templates()

    def set_completions(self, completions: List[str]) -> None:
        self.completions = completions
        self.set_module_widget.set_completions(completions)
        self.check_module_widget.set_completions(completions)

    def _dispatch_to_focused(self, method_name: str) -> None:
        widget = QApplication.focusWidget()
        if widget is not None and (self.isAncestorOf(widget) or widget is self):
            fn = getattr(widget, method_name, None)
            if callable(fn):
                fn()

    def undo(self) -> None: self._dispatch_to_focused("undo")
    def redo(self) -> None: self._dispatch_to_focused("redo")
    def cut(self) -> None: self._dispatch_to_focused("cut")
    def copy(self) -> None: self._dispatch_to_focused("copy")
    def paste(self) -> None: pass
    def selectAll(self) -> None: self._dispatch_to_focused("selectAll")

    def get_case_data(self) -> Dict[str, Any]:
        return {
            "case_info": self.case_info_widget.get_case_info(),
            "meta_info": self.meta_info_widget.get_meta_info(),
            "set_steps": self.set_module_widget.get_steps(),
            "check_steps": self.check_module_widget.get_steps(),
        }

    def set_case_data(self, case_data: Dict[str, Any]) -> None:
        self.case_info_widget.set_case_info(case_data.get("case_info", {}).get("name", ""), case_data.get("case_info", {}).get("id", ""))
        self.meta_info_widget.set_meta_info(case_data.get("meta_info", {}))
        self.set_module_widget.set_steps(case_data.get("set_steps", []))
        self.check_module_widget.set_steps(case_data.get("check_steps", []))

    def to_dsl(self) -> str:
        data = self.get_case_data()
        dsl_lines: List[str] = []
        case_info = data["case_info"]
        if case_info.get("name"):
            dsl_lines.append(f"CASE: {case_info['name']}")
        meta_parts: List[str] = []
        if case_info.get("id"):
            meta_parts.append(f"case_id={self._encode_meta_value(case_info['id'])}")
        for key in ("test_point", "priority", "owner", "scene_mapping", "scenario_id", "scenario_name", "preset_signals", "preset_scene", "preset_scene_runtime"):
            if data["meta_info"].get(key):
                meta_parts.append(f"{key}={self._encode_meta_value(data['meta_info'][key])}")
        for key in ("ai_analysis", "use_preset", "record"):
            if data["meta_info"].get(key):
                meta_parts.append(f"{key}=true")
        if meta_parts:
            dsl_lines.append("META: " + " ".join(meta_parts))
        dsl_lines.extend(["", "[SET]"])
        dsl_lines.extend(f"{step['id']}: {step['content']}" for step in data["set_steps"])
        dsl_lines.extend(["", "[CHECK]"])
        dsl_lines.extend(f"{step['id']}: {step['content']}" for step in data["check_steps"])
        return "\n".join(dsl_lines)

    def from_dsl(self, dsl_content: str) -> None:
        data = {"case_info": {"name": "", "id": ""}, "meta_info": {}, "set_steps": [], "check_steps": []}
        current_section: Optional[str] = None
        for raw in (dsl_content or "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("CASE:"):
                data["case_info"]["name"] = line[5:].strip()
                continue
            if line.startswith("META:"):
                meta_str = line[5:].strip()
                matches = list(re.finditer(r"(\w+)=", meta_str))
                for i, match in enumerate(matches):
                    key = match.group(1)
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(meta_str)
                    value = meta_str[match.end():end].strip().rstrip(",").strip()
                    if key in ("ai_analysis", "use_preset", "record"):
                        data["meta_info"][key] = value.lower() in ("true", "1", "yes")
                    elif key == "case_id":
                        data["case_info"]["id"] = value
                    else:
                        data["meta_info"][key] = value
                continue
            if line == "[SET]":
                current_section = "SET"
                continue
            if line == "[CHECK]":
                current_section = "CHECK"
                continue
            m = re.match(r"^([SC]\d+):\s*(.*)$", line)
            if m and current_section == "SET":
                data["set_steps"].append({"id": m.group(1), "content": m.group(2).strip()})
            elif m and current_section == "CHECK":
                data["check_steps"].append({"id": m.group(1), "content": m.group(2).strip()})
        self.set_case_data(data)

    def validate(self) -> List[str]:
        errors: List[str] = []
        data = self.get_case_data()
        if not data["case_info"].get("name"):
            errors.append("CASE名称不能为空")
        if not data["case_info"].get("id"):
            errors.append("CASE ID不能为空")
        if not data["meta_info"].get("test_point"):
            errors.append("测试点不能为空")
        for step in data["set_steps"]:
            if not step.get("content", "").strip():
                errors.append(f"SET步骤 {step.get('id', '')} 的内容不能为空")
        for step in data["check_steps"]:
            if not step.get("content", "").strip():
                errors.append(f"CHECK步骤 {step.get('id', '')} 的内容不能为空")
        return errors

    def _on_view_flowchart(self):
        set_steps = [s for s in self.set_module_widget.get_steps() if s.get("content", "").strip()]
        check_steps = [s for s in self.check_module_widget.get_steps() if s.get("content", "").strip()]
        dlg = FlowchartViewDialog(set_steps, check_steps, self, editor=self, save_callback=self.save_to_file_requested.emit)
        dlg.save_requested.connect(self._emit_content_changed)
        dlg.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("ModularCaseEditor Demo")
    w.resize(1200, 800)
    layout = QVBoxLayout(w)
    editor = ModularCaseEditor(w)
    editor.set_completions([
        "sys::FunctionSwitch::CSW_Enable_S",
        "sys::DriverAction::gear",
        "env::CAN 1::IPB_0x10C::VDC_Active",
        "sig::CAN 1::ADC_0x29C::CSW_Stats_S",
        "sig::CAN 1::ADC_0x29C::DNP_warning_text_info",
    ])
    layout.addWidget(editor, 1)
    btn_row = QHBoxLayout()
    btn_export = QPushButton("导出 DSL 到弹窗", w)
    btn_validate = QPushButton("校验", w)

    def _on_export():
        dlg = QDialog(w)
        dlg.setWindowTitle("导出 DSL")
        dlg.resize(900, 600)
        dialog_layout = QVBoxLayout(dlg)
        text = QTextEdit(dlg)
        text.setPlainText(editor.to_dsl())
        dialog_layout.addWidget(text, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        bb.clicked.connect(lambda: dlg.accept())
        dialog_layout.addWidget(bb)
        dlg.exec()

    def _on_validate():
        errors = editor.validate()
        QMessageBox.information(w, "校验通过", "未发现问题。") if not errors else QMessageBox.warning(w, "校验失败", "\n".join(errors))

    btn_export.clicked.connect(_on_export)
    btn_validate.clicked.connect(_on_validate)
    btn_row.addWidget(btn_export)
    btn_row.addWidget(btn_validate)
    btn_row.addStretch(1)
    layout.addLayout(btn_row)
    w.show()
    sys.exit(app.exec())
