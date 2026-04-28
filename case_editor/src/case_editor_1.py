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



