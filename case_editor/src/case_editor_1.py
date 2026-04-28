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
