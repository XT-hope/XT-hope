        if kind == "sys" and self._last_has_dot and self._dbc_parser:
            var_part, member_prefix = t.rsplit(".", 1)
            suggestions = self._dbc_parser.get_signal_completion(f"sys::{var_part}.", "sys")
            if suggestions:
                members = [s.rsplit(".", 1)[-1] for s in suggestions]
                if member_prefix:
                    members = [m for m in members if m.lower().startswith(member_prefix.lower())]
                self._last_base = var_part + "."
                self._last_prefix_segs = tuple()
                self._set_candidates(members, force_popup)
                return
        if "::" in t:
            if t.endswith("::"):
                self._last_base = t
                partial = ""
            else:
                pos = t.rfind("::")
                self._last_base = t[: pos + 2]
                partial = t[pos + 2:]
            parts = rest.split("::")
            prefix_segs = tuple([x for x in parts[:-1] if x])
            self._last_prefix_segs = prefix_segs
            children = idx.get(prefix_segs, [])
            if partial:
                children = [c for c in children if c.lower().startswith(partial.lower())]
            self._set_candidates(children, force_popup)
            return
        roots = idx.get((), [])
        if t:
            roots = [x for x in roots if x.lower().startswith(t.lower())]
        self._last_base = ""
        self._last_prefix_segs = tuple()
        self._set_candidates(roots, force_popup)

    def _on_activated(self, chosen: str) -> None:
        chosen = (chosen or "").strip().rstrip(":")
        if not chosen:
            return
        idx = self._index_by_kind.get(self._last_kind, {})
        new_text = (self._last_base + chosen) if self._last_base else chosen
        if not self._last_has_dot and idx.get(self._last_prefix_segs + (chosen,), []):
            new_text += "::"

        def apply_text() -> None:
            blocker = QSignalBlocker(self._edit)
            self._edit.setText(new_text)
            self._edit.setCursorPosition(len(new_text))
            del blocker
            self._update_candidates(new_text, force_popup=new_text.endswith("::"))

        QTimer.singleShot(0, apply_text)


_RE_CHECK_ASYNC = re.compile(r"\basync\s+(true|false)\b", re.IGNORECASE)
_RE_CHECK_WAIT = re.compile(r"\bwait\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_CHECK_TIMEOUT = re.compile(r"\btimeout(?:OfCheck)?\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_CHECK_DURATION = re.compile(r"\b(duration|checkInTime)\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_CHECK_COMMENT = re.compile(r"\bcomment\s+\"([^\"]*)\"", re.IGNORECASE)
_RE_CHECK_IN = re.compile(r"\bin\s*\[(.*?)\]\s*$", re.IGNORECASE)
_RE_CHECK_RANGE = re.compile(r"=\s*([^\s]+)\s*\.\.\s*([^\s]+)\s*$")
_RE_CHECK_SINGLE = re.compile(r"(==|!=|>=|<=|>|<|=)\s*(\S+?)(?=\s+(?:async|timeout|duration|wait|comment\b)|\s*$)", re.IGNORECASE)


def _strip_params_from_check_expr(expr: str) -> Tuple[str, Dict[str, Any]]:
    s = expr.strip()
    info: Dict[str, Any] = {"async_": False, "timeout_ms": 1000, "duration_ms": 0, "wait_ms": 0}
    for key, regex, group_offset in (
        ("async_", _RE_CHECK_ASYNC, 0),
        ("timeout_ms", _RE_CHECK_TIMEOUT, 0),
        ("duration_ms", _RE_CHECK_DURATION, 1),
        ("wait_ms", _RE_CHECK_WAIT, 0),
    ):
        m = regex.search(s)
        if not m:
            continue
        if key == "async_":
            info[key] = m.group(1).lower() == "true"
        else:
            info[key] = parse_time_to_ms(m.group(1 + group_offset) + m.group(2 + group_offset), info[key]) or info[key]
        s = regex.sub("", s).strip()
    s = _RE_CHECK_COMMENT.sub("", s).strip()
    if info.get("async_"):
        info["wait_ms"] = 0
    return s, info


def parse_check_step(text: str) -> Tuple[CheckStepModel, bool, str]:
    raw = (text or "").strip()
    if not raw:
        return CheckStepModel(items=[CheckItemModel(kind="sig", name="", mode="single")]), False, "空文本"
    comment = ""
    comment_m = _RE_CHECK_COMMENT.search(raw)
    if comment_m:
        comment = comment_m.group(1)
    tmp = _RE_CHECK_COMMENT.sub("", raw).strip()
    parts = [p.strip() for p in re.split(r"\s*&&\s*", tmp) if p.strip()]
    items: List[CheckItemModel] = []
    for p in parts:
        p2 = p[6:].strip() if p.lower().startswith("check ") else p
        expr, info = _strip_params_from_check_expr(p2)
        mode, op, single_value, list_values, range_a, range_b = "single", "==", "", [], "", ""
        m_in = _RE_CHECK_IN.search(expr)
        if m_in:
            mode = "list"
            list_values = [x.strip() for x in m_in.group(1).split(",") if x.strip()]
            name = expr[: m_in.start()].strip()
        else:
            m_range = _RE_CHECK_RANGE.search(expr)
            if m_range:
                mode = "range"
                range_a, range_b = m_range.group(1).strip(), m_range.group(2).strip()
                name = expr[: m_range.start()].strip()
            else:
                m_single = _RE_CHECK_SINGLE.search(expr)
                if m_single:
                    op, single_value = m_single.group(1), m_single.group(2).strip()
                    name = expr[: m_single.start()].strip()
                else:
                    name = expr.strip()
        kind = "env" if name.startswith("env::") else "sys" if name.startswith("sys::") else "sig"
        items.append(CheckItemModel(kind=kind, name=name, mode=mode, op=op, single_value=single_value, list_values=list_values, range_a=range_a, range_b=range_b, wait_ms=int(info["wait_ms"]), timeout_ms=int(info["timeout_ms"]), duration_ms=int(info["duration_ms"]), async_=bool(info["async_"])))
    if not items:
        return CheckStepModel(items=[CheckItemModel(kind="sig", name="", mode="single")]), False, "未解析到检查项"
    return CheckStepModel(items=items, comment=comment), True, ""


def render_check_step(model: CheckStepModel) -> str:
    chunks: List[str] = []
    for i, it in enumerate(model.items):
        name = (it.name or "").strip()
        if it.kind == "sig" and name and not name.startswith("sig::"):
            name = "sig::" + name if "::" in name else name
        if it.kind == "env" and name and not name.startswith("env::"):
            name = "env::" + name if "::" in name else name
        if it.kind == "sys" and name and not name.startswith("sys::"):
            name = "sys::" + name if "::" in name else name
        expr = f"check {name}".rstrip() if i == 0 else name.rstrip()
        if it.mode == "list":
            expr += " in [" + ",".join(x.strip() for x in it.list_values if x.strip()) + "]"
        elif it.mode == "range":
            expr += f"={(it.range_a or '').strip()}..{(it.range_b or '').strip()}"
        else:
            expr += f"{(it.op or '==').strip()}{(it.single_value or '').strip()}"
        if not it.async_ and int(it.wait_ms or 0) > 0:
            expr += f" wait {int(it.wait_ms)}ms"
        expr += f" timeout {int(it.timeout_ms or 1000)}ms"
        if int(it.duration_ms or 0) > 0:
            expr += f" duration {int(it.duration_ms)}ms"
        expr += f" async {'true' if it.async_ else 'false'}"
        chunks.append(expr.strip())
    out = " && ".join(chunks).strip()
    if model.comment:
        out += f' comment "{model.comment}"'
    return out



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
