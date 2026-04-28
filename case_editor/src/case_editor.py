from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json
import re
import sys

from PyQt6.QtCore import QPointF, QRectF, QStringListModel, QSignalBlocker, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QAbstractItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)


class ReadOnlyLineEdit(QLineEdit):
    """只读文本输入框，不支持粘贴操作。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_V and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            return
        super().keyPressEvent(event)


FORM_LABEL_WIDTH = 80
FORM_HSPACING = 6
FORM_VSPACING = 6


def _setup_groupbox_style(group: QGroupBox) -> None:
    group.setStyleSheet(
        """
        QGroupBox {
            font-weight: bold;
            font-size: 14px;
            border: 2px solid #cccccc;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        """
    )


def _align_form_layout(form_layout: QFormLayout) -> None:
    form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_layout.setHorizontalSpacing(FORM_HSPACING)
    form_layout.setVerticalSpacing(FORM_VSPACING)
    form_layout.setContentsMargins(0, 0, 0, 0)


def _fix_label_for_field(form_layout: QFormLayout, field_widget: QWidget) -> None:
    lbl = form_layout.labelForField(field_widget)
    if lbl is None:
        return
    lbl.setFixedWidth(FORM_LABEL_WIDTH)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def _setup_scroll(scroll: QScrollArea) -> None:
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setContentsMargins(0, 0, 0, 0)
    scroll.setViewportMargins(0, 0, 0, 0)
    scroll.setStyleSheet("QScrollArea { border: none; }")


_TIME_RE = re.compile(r"^\s*(\d+)\s*(ms|s)?\s*$", re.IGNORECASE)


def parse_time_to_ms(s: str, default_ms: Optional[int] = None) -> Optional[int]:
    if s is None:
        return default_ms
    s = str(s).strip()
    if not s:
        return default_ms
    m = _TIME_RE.match(s)
    if not m:
        return default_ms
    n = int(m.group(1))
    unit = (m.group(2) or "ms").lower()
    return n * 1000 if unit == "s" else n


def fmt_ms(ms: Optional[int]) -> str:
    return f"{int(ms)}ms" if ms is not None else ""


@dataclass
class SetSignalModel:
    kind: str
    name: str
    value: str


@dataclass
class SetStepModel:
    signals: List[SetSignalModel] = field(default_factory=list)
    wait_ms: int = 0
    next_checks: List[str] = field(default_factory=list)
    comment: str = ""


@dataclass
class CheckItemModel:
    kind: str
    name: str
    mode: str
    op: str = "=="
    single_value: str = ""
    list_values: List[str] = field(default_factory=list)
    range_a: str = ""
    range_b: str = ""
    wait_ms: int = 0
    timeout_ms: int = 1000
    duration_ms: int = 0
    async_: bool = False


@dataclass
class CheckStepModel:
    items: List[CheckItemModel] = field(default_factory=list)
    comment: str = ""


_RE_SET_WAIT = re.compile(r"\bwait\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_SET_THEN = re.compile(r"\bthen\s+check\s+([A-Za-z0-9_,\s]+?)(?:\s+\bcomment\b|$)", re.IGNORECASE)
_RE_SET_COMMENT = re.compile(r"\s+\bcomment\s+\"([^\"]*)\"\s*$", re.IGNORECASE)


def parse_set_step(text: str) -> Tuple[SetStepModel, bool, str]:
    raw = (text or "").strip()
    if not raw:
        return SetStepModel(signals=[SetSignalModel(kind="sys", name="", value="")]), False, "空文本"

    wait_ms = 0
    next_checks: List[str] = []
    comment = ""

    comment_m = _RE_SET_COMMENT.search(raw)
    if comment_m:
        comment = comment_m.group(1)
        raw = _RE_SET_COMMENT.sub("", raw).strip()

    wait_m = _RE_SET_WAIT.search(raw)
    if wait_m:
        wait_ms = parse_time_to_ms(wait_m.group(1) + wait_m.group(2), default_ms=0) or 0
        raw = _RE_SET_WAIT.sub("", raw).strip()

    then_m = _RE_SET_THEN.search(raw)
    if then_m:
        ids = [x.strip() for x in then_m.group(1).split(",") if x.strip()]
        next_checks = [x if x.upper().startswith("C") else x for x in ids]
        raw = _RE_SET_THEN.sub("", raw).strip()

    signals: List[SetSignalModel] = []
    for part in [p.strip() for p in raw.split(" && ") if p.strip()]:
        if part.lower().startswith("set "):
            part = part[4:].strip()
        name, value = (part.split("=", 1) + [""])[:2] if "=" in part else (part, "")
        name = name.strip()
        value = value.strip()
        kind = "env" if name.startswith("env::") else "sys"
        signals.append(SetSignalModel(kind=kind, name=name, value=value))

    if not signals:
        return SetStepModel(signals=[SetSignalModel(kind="sys", name="", value="")]), False, "未解析到信号"
    return SetStepModel(signals=signals, wait_ms=wait_ms, next_checks=next_checks, comment=comment), True, ""


def render_set_step(model: SetStepModel) -> str:
    chunks: List[str] = []
    for i, signal in enumerate(model.signals):
        name = (signal.name or "").strip()
        value = (signal.value or "").strip()
        if signal.kind == "sys" and name and not name.startswith("sys::"):
            name = "sys::" + name if "::" in name else name
        if signal.kind == "env" and name and not name.startswith("env::"):
            name = "env::" + name if name.startswith("CAN ") or "::" in name else name
        prefix = "set " if i == 0 else ""
        chunks.append(f"{prefix}{name}={value}" if name else f"{prefix}")
    out = " && ".join(chunks).strip()
    if int(model.wait_ms or 0) > 0:
        out += f" wait {int(model.wait_ms)}ms"
    if model.next_checks:
        out += " then check " + ",".join(c.strip() for c in model.next_checks if c.strip())
    if model.comment:
        out += f' comment "{model.comment}"'
    return out.strip()


def _build_hier_index_by_kind(completions_by_kind: Dict[str, List[str]]) -> Dict[str, Dict[Tuple[str, ...], List[str]]]:
    out: Dict[str, Dict[Tuple[str, ...], List[str]]] = {}
    for kind, paths in (completions_by_kind or {}).items():
        idx: Dict[Tuple[str, ...], set[str]] = {}
        for p in paths or []:
            if not isinstance(p, str):
                continue
            parts = [x for x in p.split("::") if x]
            if not parts:
                continue
            real_kind, segs = (parts[0], parts[1:]) if parts[0] in ("sys", "sig", "env") else (kind, parts)
            if real_kind != kind:
                continue
            for i in range(len(segs)):
                idx.setdefault(tuple(segs[:i]), set()).add(segs[i])
        out[kind] = {k: sorted(v, key=lambda s: s.lower()) for k, v in idx.items()}
    return out


class _HierLineEditCompleter:
    """QLineEdit 的逐级补全控制器。"""

    def __init__(self, edit: QLineEdit, kind_getter, index_by_kind: Dict[str, Dict[Tuple[str, ...], List[str]]], allowed_kinds: List[str], dbc_parser=None) -> None:
        self._edit = edit
        self._kind_getter = kind_getter
        self._index_by_kind = index_by_kind or {}
        self._allowed_kinds = [k for k in (allowed_kinds or []) if k in self._index_by_kind]
        self._dbc_parser = dbc_parser
        self._model = QStringListModel(self._edit)
        self._completer = QCompleter(self._model, self._edit)
        try:
            self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        except AttributeError:
            self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._edit.setCompleter(self._completer)
        self._last_base = ""
        self._last_kind = ""
        self._last_prefix_segs: Tuple[str, ...] = tuple()
        self._last_has_dot = False
        self._edit.textEdited.connect(self._on_text_edited)
        self._completer.activated[str].connect(self._on_activated)
        self._update_candidates(self._edit.text(), force_popup=False)

    def refresh(self) -> None:
        self._update_candidates(self._edit.text(), force_popup=False)

    def _detect_kind_and_rest(self, text: str) -> Tuple[str, str]:
        default_kind = (self._kind_getter() or "").strip()
        if default_kind not in self._allowed_kinds and self._allowed_kinds:
            default_kind = self._allowed_kinds[0]
        return default_kind, text or ""

    def _set_candidates(self, items: List[str], force_popup: bool) -> None:
        self._model.setStringList(items or [])
        self._completer.setCompletionPrefix("")
        if force_popup and items and self._edit.hasFocus():
            self._completer.complete()

    def _on_text_edited(self, text: str) -> None:
        self._update_candidates(text, force_popup=True)

    def _update_candidates(self, text: str, force_popup: bool) -> None:
        t = text or ""
        kind, rest = self._detect_kind_and_rest(t)
        self._last_kind = kind
        self._last_has_dot = "." in t
        idx = self._index_by_kind.get(kind, {})
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
