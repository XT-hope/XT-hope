from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel, QSignalBlocker, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFormLayout,
)


# ----------------------------
# 布局对齐参数
# ----------------------------
FORM_LABEL_WIDTH = 80
FORM_HSPACING = 6
FORM_VSPACING = 6
ROW_FIELD_HEIGHT = 30


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


def _set_uniform_height(*widgets: QWidget, height: int = ROW_FIELD_HEIGHT) -> None:
    for w in widgets:
        if w is not None:
            w.setFixedHeight(height)


def _style_dialog_secondary_btn(btn: QPushButton) -> None:
    btn.setMinimumWidth(96)
    btn.setFixedHeight(32)
    btn.setStyleSheet(
        """
        QPushButton {
            background: #ffffff;
            border: 1px solid #cfd7e3;
            border-radius: 5px;
            color: #243447;
            padding: 4px 14px;
        }
        QPushButton:hover {
            background: #f5f8fc;
            border-color: #aebbcf;
        }
        """
    )


def _style_dialog_primary_btn(btn: QPushButton) -> None:
    btn.setMinimumWidth(96)
    btn.setFixedHeight(32)
    btn.setStyleSheet(
        """
        QPushButton {
            background: #2f80ed;
            border: 1px solid #2f80ed;
            border-radius: 5px;
            color: #ffffff;
            padding: 4px 14px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #256ecf;
            border-color: #256ecf;
        }
        """
    )


def _style_add_btn(btn: QPushButton) -> None:
    btn.setMinimumWidth(106)
    btn.setFixedHeight(32)
    btn.setStyleSheet(
        """
        QPushButton {
            background: #2f80ed;
            border: 1px solid #2f80ed;
            border-radius: 5px;
            color: #ffffff;
            font-weight: bold;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background: #256ecf;
            border-color: #256ecf;
        }
        """
    )


# ----------------------------
# 时间解析/格式化
# ----------------------------
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


# ----------------------------
# DSL 数据模型
# ----------------------------
@dataclass
class SetSignalModel:
    kind: str  # "env" | "sys"
    name: str
    value: str


@dataclass
class SetStepModel:
    signals: List[SetSignalModel] = field(default_factory=list)
    wait_ms: int = 0
    next_checks: List[str] = field(default_factory=list)  # e.g. ["C1", "C2"]


@dataclass
class CheckItemModel:
    kind: str  # "sig" | "env" | "sys"
    name: str

    mode: str  # "single" | "list" | "range"
    op: str = "=="  # for single: "==", ">", "<", ">=", "<=", "="

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


# ----------------------------
# SET DSL 解析/生成
# ----------------------------
_RE_SET_WAIT = re.compile(r"\bwait\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_SET_THEN = re.compile(r"\bthen\s+check\s+([A-Za-z0-9_,\s]+)\b", re.IGNORECASE)


def parse_set_step(text: str) -> Tuple[SetStepModel, bool, str]:
    raw = (text or "").strip()
    if not raw:
        return SetStepModel(signals=[SetSignalModel(kind="sys", name="", value="")]), False, "空文本"

    wait_ms = 0
    next_checks: List[str] = []

    wait_m = _RE_SET_WAIT.search(raw)
    if wait_m:
        wait_ms = parse_time_to_ms(wait_m.group(1) + wait_m.group(2), default_ms=0) or 0

    then_m = _RE_SET_THEN.search(raw)
    if then_m:
        part = then_m.group(1)
        ids = [x.strip() for x in part.split(",") if x.strip()]
        next_checks = [x if x.upper().startswith("C") else x for x in ids]

    # 去掉 wait / then check，剩余部分解析 signals
    tmp = raw
    tmp = _RE_SET_THEN.sub("", tmp)
    tmp = _RE_SET_WAIT.sub("", tmp)
    tmp = tmp.strip()

    parts = [p.strip() for p in tmp.split(";") if p.strip()]
    signals: List[SetSignalModel] = []

    # 支持：set sys::A::B=1 或 sys::A::B=1
    for p in parts:
        p2 = p.strip()
        if p2.lower().startswith("set "):
            p2 = p2[4:].strip()

        if "=" not in p2:
            # 允许用户输入不完整
            name = p2.strip()
            val = ""
        else:
            name, val = p2.split("=", 1)
            name = name.strip()
            val = val.strip()

        kind = "sys"
        if name.startswith("env::"):
            kind = "env"
        elif name.startswith("sys::"):
            kind = "sys"
        signals.append(SetSignalModel(kind=kind, name=name, value=val))

    if not signals:
        return SetStepModel(signals=[SetSignalModel(kind="sys", name="", value="")]), False, "未解析到信号"

    return SetStepModel(signals=signals, wait_ms=wait_ms, next_checks=next_checks), True, ""


def render_set_step(model: SetStepModel) -> str:
    chunks: List[str] = []
    for s in model.signals:
        name = (s.name or "").strip()
        value = (s.value or "").strip()

        # 若用户只填了 FunctionSwitch::X，也允许；但生成时尽量带前缀
        if s.kind == "sys" and name and not name.startswith("sys::"):
            name = "sys::" + name if "::" in name else name
        if s.kind == "env" and name and not name.startswith("env::"):
            name = "env::" + name if name.startswith("CAN ") or "::" in name else name

        if name and value:
            chunks.append(f"set {name}={value}")
        elif name and not value:
            chunks.append(f"set {name}=")
        else:
            chunks.append("set ")

    out = " ; ".join(chunks).strip()

    if int(model.wait_ms or 0) > 0:
        out += f" wait {int(model.wait_ms)}ms"

    if model.next_checks:
        out += " then check " + ",".join([c.strip() for c in model.next_checks if c.strip()])

    return out.strip()

def _build_hier_index_by_kind(completions_by_kind: Dict[str, List[str]]) -> Dict[str, Dict[Tuple[str, ...], List[str]]]:
    """
    把类似：
      sys::FunctionSwitch::CSW_Enable_S
      sys::simulink::Ego_PosX
    构造成分层索引：
      index["sys"][()] -> ["FunctionSwitch", "simulink", ...]
      index["sys"][("simulink",)] -> ["Ego_PosX", "Ego_PosY", ...]
    """
    out: Dict[str, Dict[Tuple[str, ...], List[str]]] = {}
 
    for kind, paths in (completions_by_kind or {}).items():
        idx: Dict[Tuple[str, ...], set[str]] = {}
        for p in paths or []:
            if not isinstance(p, str):
                continue
            parts = [x for x in p.split("::") if x]  # 去掉空段（含末尾 ::）
            if not parts:
                continue
 
            # paths 通常已经按 kind 分组了；这里仍做一次兼容判断
            if parts[0] in ("sys", "sig", "env"):
                real_kind = parts[0]
                segs = parts[1:]
            else:
                real_kind = kind
                segs = parts
 
            if real_kind != kind:
                continue
 
            for i in range(len(segs)):
                prefix = tuple(segs[:i])
                idx.setdefault(prefix, set()).add(segs[i])
 
        out[kind] = {k: sorted(v, key=lambda s: s.lower()) for k, v in idx.items()}
 
    return out
 
 
class _HierLineEditCompleter:
    """
    QLineEdit 的逐级补全控制器：
    - model 里放"下一层 segment"（不放完整路径）
    - 使用 UnfilteredPopupCompletion，避免 QCompleter 用整行做二次过滤
    - 显式连接 activated[str]，避免选中后 QLineEdit 默认覆盖导致前缀丢失
    """
 
    def __init__(
        self,
        edit: QLineEdit,
        kind_getter,
        index_by_kind: Dict[str, Dict[Tuple[str, ...], List[str]]],
        allowed_kinds: List[str],
    ) -> None:
        self._edit = edit
        self._kind_getter = kind_getter
        self._index_by_kind = index_by_kind or {}
        self._allowed_kinds = [k for k in (allowed_kinds or []) if k in self._index_by_kind]
 
        self._model = QStringListModel(self._edit)
        self._completer = QCompleter(self._model, self._edit)
 
        # 关键点：不要让 completer 用"整行文本"二次过滤 segment 候选
        try:
            self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        except AttributeError:
            # 兼容部分 PyQt6 版本
            self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
 
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._edit.setCompleter(self._completer)
 
        # 状态：用于 activated 时判断是否需要补 "::"
        self._last_base = ""
        self._last_kind = ""
        self._last_prefix_segs: Tuple[str, ...] = tuple()
        self._last_has_sep = False
 
        self._edit.textEdited.connect(self._on_text_edited)
 
        # 关键点：显式连接 str 重载，避免前缀被默认插入行为覆盖
        self._completer.activated[str].connect(self._on_activated)
 
        self._update_candidates(self._edit.text(), force_popup=False)
 
    def refresh(self) -> None:
        self._update_candidates(self._edit.text(), force_popup=False)
 
    def _detect_kind_and_rest(self, text: str) -> Tuple[str, str]:
        t = text or ""
        for k in self._allowed_kinds:
            prefix = k + "::"
            if t.startswith(prefix):
                return k, t[len(prefix) :]
        default_kind = (self._kind_getter() or "").strip()
        if default_kind not in self._allowed_kinds and self._allowed_kinds:
            default_kind = self._allowed_kinds[0]
        return default_kind, t
 
    def _set_candidates(self, items: List[str], force_popup: bool) -> None:
        self._model.setStringList(items or [])
 
        # 兜底：再禁一次 prefix 过滤
        self._completer.setCompletionPrefix("")
 
        if force_popup and items and self._edit.hasFocus():
            self._completer.complete()
 
    def _on_text_edited(self, text: str) -> None:
        self._update_candidates(text, force_popup=True)
 
    def _update_candidates(self, text: str, force_popup: bool) -> None:
        t = text or ""
        has_sep = "::" in t
        self._last_has_sep = has_sep
 
        kind, rest = self._detect_kind_and_rest(t)
        self._last_kind = kind
        idx = self._index_by_kind.get(kind, {})
 
        # base / partial：用于"替换当前 segment"
        if has_sep:
            if t.endswith("::"):
                self._last_base = t
                partial = ""
            else:
                pos = t.rfind("::")
                self._last_base = t[: pos + 2]
                partial = t[pos + 2 :]
        else:
            self._last_base = ""
            partial = t
 
        # 1) 没有 ::：提示 kind（sys/env/sig）或当前 kind 的第一层
        if not has_sep:
            p = (partial or "").strip()
            kind_hits = [k for k in self._allowed_kinds if k.lower().startswith(p.lower())] if p else []
            if kind_hits:
                self._last_prefix_segs = tuple()
                self._set_candidates(kind_hits, force_popup)
                return
 
            roots = idx.get((), [])
            if p:
                roots = [x for x in roots if x.lower().startswith(p.lower())]
            self._last_prefix_segs = tuple()
            self._set_candidates(roots, force_popup)
            return
 
        # 2) 有 ::：按层级提示下一段 children
        parts = rest.split("::")
        ends_with_sep = t.endswith("::")
 
        if ends_with_sep:
            prefix_segs = tuple([x for x in parts[:-1] if x])
            seg_partial = ""
        else:
            prefix_segs = tuple([x for x in parts[:-1] if x])
            seg_partial = parts[-1] if parts else ""
 
        self._last_prefix_segs = prefix_segs
 
        children = idx.get(prefix_segs, [])
        if seg_partial:
            children = [c for c in children if c.lower().startswith(seg_partial.lower())]
 
        self._set_candidates(children, force_popup)
 
    def _on_activated(self, chosen: str) -> None:
        chosen = (chosen or "").strip()
        if not chosen:
            return
 
        chosen = chosen.rstrip(":")
        idx = self._index_by_kind.get(self._last_kind, {})
 
        # A) 还没出现 ::，且用户选中了 kind（sys/env/sig）
        if not self._last_has_sep and chosen in self._allowed_kinds:
            new_text = chosen + "::"
            # 使用 QTimer 延迟执行，避免 QCompleter 默认行为覆盖
            def apply_text():
                blocker = QSignalBlocker(self._edit)
                self._edit.setText(new_text)
                self._edit.setCursorPosition(len(new_text))
                del blocker
                self._update_candidates(new_text, force_popup=True)
            QTimer.singleShot(0, apply_text)
            return
 
        # B) 替换当前 segment：base + chosen
        new_text = (self._last_base + chosen) if self._last_base else chosen
 
        # 如果 chosen 下面还有子节点，自动补 "::"
        if idx.get(self._last_prefix_segs + (chosen,), []):
            if not new_text.endswith("::"):
                new_text += "::"
 
        # 使用 QTimer 延迟执行，避免 QCompleter 默认行为覆盖
        def apply_text():
            blocker = QSignalBlocker(self._edit)
            self._edit.setText(new_text)
            self._edit.setCursorPosition(len(new_text))
            del blocker
            self._update_candidates(new_text, force_popup=new_text.endswith("::"))
        QTimer.singleShot(0, apply_text)

# ----------------------------
# CHECK DSL 解析/生成
# ----------------------------
_RE_CHECK_ASYNC = re.compile(r"\basync\s+(true|false)\b", re.IGNORECASE)
_RE_CHECK_WAIT = re.compile(r"\bwait\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_CHECK_TIMEOUT = re.compile(r"\btimeout(?:OfCheck)?\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)
_RE_CHECK_DURATION = re.compile(r"\b(duration|checkInTime)\s+(\d+)\s*(ms|s)\b", re.IGNORECASE)

_RE_CHECK_IN = re.compile(r"\bin\s*\[(.*?)\]\s*$", re.IGNORECASE)
_RE_CHECK_RANGE = re.compile(r"=\s*([^\s]+)\s*\.\.\s*([^\s]+)\s*$")
_RE_CHECK_SINGLE = re.compile(r"(==|>=|<=|>|<|=)\s*([^\s]+)\s*$")


def _strip_params_from_check_expr(expr: str) -> Tuple[str, Dict[str, Any]]:
    s = expr.strip()
    info: Dict[str, Any] = {}

    m = _RE_CHECK_ASYNC.search(s)
    if m:
        info["async_"] = m.group(1).lower() == "true"
        s = _RE_CHECK_ASYNC.sub("", s).strip()
    else:
        info["async_"] = False

    m = _RE_CHECK_TIMEOUT.search(s)
    if m:
        info["timeout_ms"] = parse_time_to_ms(m.group(1) + m.group(2), default_ms=1000) or 1000
        s = _RE_CHECK_TIMEOUT.sub("", s).strip()
    else:
        info["timeout_ms"] = 1000

    m = _RE_CHECK_DURATION.search(s)
    if m:
        info["duration_ms"] = parse_time_to_ms(m.group(2) + m.group(3), default_ms=0) or 0
        s = _RE_CHECK_DURATION.sub("", s).strip()
    else:
        info["duration_ms"] = 0

    m = _RE_CHECK_WAIT.search(s)
    if m:
        info["wait_ms"] = parse_time_to_ms(m.group(1) + m.group(2), default_ms=0) or 0
        s = _RE_CHECK_WAIT.sub("", s).strip()
    else:
        info["wait_ms"] = 0

    # async=true 时 wait 不生效
    if info.get("async_"):
        info["wait_ms"] = 0

    return s.strip(), info


def parse_check_step(text: str) -> Tuple[CheckStepModel, bool, str]:
    raw = (text or "").strip()
    if not raw:
        return CheckStepModel(items=[CheckItemModel(kind="sig", name="", mode="single")]), False, "空文本"

    # 允许：第一段有 "check "，后续段可能省略 "check "
    parts = [p.strip() for p in re.split(r"\s*&&\s*", raw) if p.strip()]
    items: List[CheckItemModel] = []

    for p in parts:
        p2 = p.strip()
        if p2.lower().startswith("check "):
            p2 = p2[6:].strip()

        # 先提取 async/timeout/duration/wait
        expr, info = _strip_params_from_check_expr(p2)

        # 判断值模式
        mode = "single"
        op = "=="
        single_value = ""
        list_values: List[str] = []
        range_a = ""
        range_b = ""

        # list: "... in [1,2,3]"
        m_in = _RE_CHECK_IN.search(expr)
        if m_in:
            mode = "list"
            inside = m_in.group(1).strip()
            list_values = [x.strip() for x in inside.split(",") if x.strip()]
            name = expr[: m_in.start()].strip()
        else:
            # range: "... = a .. b"
            m_range = _RE_CHECK_RANGE.search(expr)
            if m_range:
                mode = "range"
                range_a = m_range.group(1).strip()
                range_b = m_range.group(2).strip()
                name = expr[: m_range.start()].strip()
            else:
                m_single = _RE_CHECK_SINGLE.search(expr)
                if m_single:
                    mode = "single"
                    op = m_single.group(1)
                    single_value = m_single.group(2).strip()
                    name = expr[: m_single.start()].strip()
                else:
                    # 解析失败时：尽量把整个 expr 当 name
                    name = expr.strip()

        kind = "sig"
        if name.startswith("env::"):
            kind = "env"
        elif name.startswith("sys::"):
            kind = "sys"
        elif name.startswith("sig::"):
            kind = "sig"

        items.append(
            CheckItemModel(
                kind=kind,
                name=name,
                mode=mode,
                op=op,
                single_value=single_value,
                list_values=list_values,
                range_a=range_a,
                range_b=range_b,
                wait_ms=int(info.get("wait_ms") or 0),
                timeout_ms=int(info.get("timeout_ms") or 1000),
                duration_ms=int(info.get("duration_ms") or 0),
                async_=bool(info.get("async_") or False),
            )
        )

    if not items:
        return CheckStepModel(items=[CheckItemModel(kind="sig", name="", mode="single")]), False, "未解析到检查项"

    return CheckStepModel(items=items), True, ""


def render_check_step(model: CheckStepModel) -> str:
    chunks: List[str] = []
    for it in model.items:
        name = (it.name or "").strip()

        # 尽量带前缀
        if it.kind in ("sig", "env", "sys"):
            if it.kind == "sig" and name and not name.startswith("sig::"):
                name = "sig::" + name if "::" in name else name
            if it.kind == "env" and name and not name.startswith("env::"):
                name = "env::" + name if "::" in name else name
            if it.kind == "sys" and name and not name.startswith("sys::"):
                name = "sys::" + name if "::" in name else name

        expr = f"check {name}".rstrip()

        if it.mode == "list":
            expr += " in [" + ",".join([x.strip() for x in it.list_values if x.strip()]) + "]"
        elif it.mode == "range":
            a = (it.range_a or "").strip()
            b = (it.range_b or "").strip()
            expr += f"={a}..{b}"
        else:
            op = (it.op or "==").strip()
            v = (it.single_value or "").strip()
            expr += f"{op}{v}"

        # 参数：timeout 默认 1000ms，但生成时仍显式输出，便于可读/可控
        timeout_ms = int(it.timeout_ms or 1000)
        duration_ms = int(it.duration_ms or 0)
        wait_ms = int(it.wait_ms or 0)
        async_ = bool(it.async_)

        if not async_ and wait_ms > 0:
            expr += f" wait {wait_ms}ms"

        expr += f" timeout {timeout_ms}ms"

        if duration_ms > 0:
            expr += f" duration {duration_ms}ms"

        expr += f" async {'true' if async_ else 'false'}"

        chunks.append(expr.strip())

    return " && ".join(chunks).strip()


# ----------------------------
# Step 编辑弹窗：SET
# ----------------------------
class SetSignalRow(QWidget):
    removed = pyqtSignal(object)
    KIND_WIDTH = 96
    VALUE_WIDTH = 220
    ACTION_WIDTH = 76
 
    def __init__(
        self,
        completions_by_kind: Dict[str, List[str]],
        hier_index_by_kind: Dict[str, Dict[Tuple[str, ...], List[str]]],
        parent=None,
        dbc_parser=None,
    ):
        super().__init__(parent)
        self._completions_by_kind = completions_by_kind
        self._hier_index_by_kind = hier_index_by_kind
        self._dbc_parser = dbc_parser
        self._build_ui()
 
    def _build_ui(self) -> None:
        self.setObjectName("setSignalRowCard")
        self.setStyleSheet(
            """
            QWidget#setSignalRowCard {
                background-color: #ffffff;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
            }
            QWidget#setSignalRowCard QLineEdit,
            QWidget#setSignalRowCard QComboBox {
                background: #fbfcfe;
                border: 1px solid #cad5e3;
                border-radius: 4px;
                padding: 2px 8px;
            }
            QWidget#setSignalRowCard QLineEdit:focus,
            QWidget#setSignalRowCard QComboBox:focus {
                border: 1px solid #5b9cff;
                background: #ffffff;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        root.addLayout(layout)
 
        self.kind_combo = QComboBox(self)
        self.kind_combo.addItems(["env", "sys"])
        self.kind_combo.setFixedWidth(self.KIND_WIDTH)
        layout.addWidget(self.kind_combo)
 
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("信号名称（支持逐级补全）")
        self.name_edit.setMinimumWidth(340)
        layout.addWidget(self.name_edit, 1)
 
        self.value_edit = QLineEdit(self)
        self.value_edit.setPlaceholderText("值（如 0x1 / 1 / true）")
        self.value_edit.setFixedWidth(self.VALUE_WIDTH)
        layout.addWidget(self.value_edit)
 
        btn_del = QPushButton("删除", self)
        btn_del.setFixedWidth(self.ACTION_WIDTH)
        btn_del.setStyleSheet(
            """
            QPushButton {
                background: #ffefef;
                border: 1px solid #f0b9b9;
                border-radius: 4px;
                color: #b42318;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ffe3e3;
                border-color: #e19d9d;
            }
            """
        )
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(btn_del)

        _set_uniform_height(self.kind_combo, self.name_edit, self.value_edit, btn_del)
 
        # 逐级补全（只对 name_edit）
        try:
            self._hier = _HierLineEditCompleter(
                edit=self.name_edit,
                kind_getter=lambda: self.kind_combo.currentText(),
                index_by_kind=self._hier_index_by_kind,
                allowed_kinds=["env", "sys"],
                dbc_parser=self._dbc_parser,
            )
        except TypeError:
            self._hier = _HierLineEditCompleter(
                edit=self.name_edit,
                kind_getter=lambda: self.kind_combo.currentText(),
                index_by_kind=self._hier_index_by_kind,
                allowed_kinds=["env", "sys"],
            )
        self.kind_combo.currentTextChanged.connect(lambda _k: self._hier.refresh())
 
    def set_data(self, s: SetSignalModel) -> None:
        kind = s.kind if s.kind in ("env", "sys") else "sys"
        self.kind_combo.setCurrentText(kind)
        name = s.name or ""
        if name.startswith("sys::"):
            name = name[5:]
        elif name.startswith("env::"):
            name = name[5:]
        self.name_edit.setText(name)
        self.value_edit.setText(s.value or "")
        self._hier.refresh()
 
    def get_data(self) -> SetSignalModel:
        kind = self.kind_combo.currentText()
        name = self.name_edit.text().strip()
        if name and not name.startswith("sys::") and not name.startswith("env::"):
            name = f"{kind}::{name}"
        return SetSignalModel(
            kind=kind,
            name=name,
            value=self.value_edit.text().strip(),
        )

class SetStepDialog(QDialog):
    def __init__(
        self,
        raw_text: str,
        completions_by_kind: Dict[str, List[str]],
        available_check_ids: List[str],
        parent=None,
        dbc_parser=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("编辑 SET Step")
        self.resize(900, 600)

        self._raw_text = raw_text or ""
        self._completions_by_kind = completions_by_kind
        self._hier_index_by_kind = _build_hier_index_by_kind(self._completions_by_kind)
        self._available_check_ids = available_check_ids
        self._dbc_parser = dbc_parser

        self._model = SetStepModel(signals=[SetSignalModel(kind="sys", name="", value="")], wait_ms=0, next_checks=[])
        self._parsed_ok = False
        self._parse_msg = ""

        self._build_ui()
        self._try_parse_and_fill()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.tip = QLabel("", self)
        self.tip.setStyleSheet("color: #b00020;")
        self.tip.setWordWrap(True)
        layout.addWidget(self.tip)

        step_box = QGroupBox("Step 参数", self)
        _setup_groupbox_style(step_box)
        step_l = QFormLayout(step_box)
        _align_form_layout(step_l)

        self.wait_spin = QSpinBox(step_box)
        self.wait_spin.setRange(0, 10_000_000)
        self.wait_spin.setSuffix(" ms（0 表示不输出）")
        step_l.addRow("wait:", self.wait_spin)
        _fix_label_for_field(step_l, self.wait_spin)

        row_next = QWidget(step_box)
        row_next_l = QHBoxLayout(row_next)
        row_next_l.setContentsMargins(0, 0, 0, 0)
        row_next_l.setSpacing(6)

        self.next_check_enable = QCheckBox("启用 then check", row_next)
        self.next_checks_edit = QLineEdit(step_box)
        self.next_checks_edit.setPlaceholderText("输入 C1,C2...（可选）")
        self.next_checks_edit.setEnabled(False)

        self.next_check_enable.toggled.connect(self.next_checks_edit.setEnabled)

        row_next_l.addWidget(self.next_check_enable)
        row_next_l.addWidget(self.next_checks_edit, 1)

        step_l.addRow("next check:", row_next)
        _fix_label_for_field(step_l, row_next)

        if self._available_check_ids:
            hint = QLabel(f"可用 CHECK：{', '.join(self._available_check_ids)}", step_box)
            hint.setStyleSheet("color: #666666;")
            hint.setWordWrap(True)
            step_l.addRow("", hint)

        layout.addWidget(step_box)

        sig_box = QGroupBox("SET 信号列表", self)
        _setup_groupbox_style(sig_box)
        sig_l = QVBoxLayout(sig_box)

        sig_header = QWidget(sig_box)
        sig_header_l = QHBoxLayout(sig_header)
        sig_header_l.setContentsMargins(0, 0, 0, 0)
        sig_header_l.setSpacing(6)
        sig_hint = QLabel("可添加多条；wait/then check 仅对整个 step 生效", sig_box)
        sig_hint.setStyleSheet("color: #666666;")
        sig_hint.setWordWrap(True)
        btn_add = QPushButton("添加 signal", sig_box)
        btn_add.clicked.connect(self._add_row)
        sig_header_l.addWidget(sig_hint, 1)
        sig_header_l.addWidget(btn_add)
        sig_l.addWidget(sig_header)

        self.sig_scroll = QScrollArea(sig_box)
        _setup_scroll(self.sig_scroll)

        self.sig_container = QWidget(self.sig_scroll)
        self.sig_container.setContentsMargins(0, 0, 0, 0)

        self.sig_layout = QVBoxLayout(self.sig_container)
        self.sig_layout.setContentsMargins(0, 0, 0, 0)
        self.sig_layout.setSpacing(6)
        self.sig_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.sig_scroll.setWidget(self.sig_container)
        sig_l.addWidget(self.sig_scroll, 1)

        layout.addWidget(sig_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _set_tip(self, msg: str) -> None:
        self.tip.setText(msg or "")

    def _clear_rows(self) -> None:
        while self.sig_layout.count():
            item = self.sig_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_row(self, data: Optional[SetSignalModel] = None) -> None:
        row = SetSignalRow(
            self._completions_by_kind,
            self._hier_index_by_kind,
            parent=self.sig_container,
            dbc_parser=self._dbc_parser,
        )
        row.removed.connect(self._remove_row)
    
        if isinstance(data, SetSignalModel):
            row.set_data(data)
    
        self.sig_layout.addWidget(row)

    def _remove_row(self, row: SetSignalRow) -> None:
        if self.sig_layout.count() <= 1:
            row.set_data(SetSignalModel(kind="sys", name="", value=""))
            return
        self.sig_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _try_parse_and_fill(self) -> None:
        model, ok, msg = parse_set_step(self._raw_text)
        self._model = model
        self._parsed_ok = ok
        self._parse_msg = msg
 
        if not ok:
            self._set_tip("当前文本无法完全解析，将以表单内容重新生成并覆盖主界面文本。")
        else:
            self._set_tip("")
 
        self.wait_spin.setValue(int(self._model.wait_ms or 0))
        if self._model.next_checks:
            self.next_check_enable.setChecked(True)
            self.next_checks_edit.setEnabled(True)
            self.next_checks_edit.setText(",".join(self._model.next_checks))
        else:
            self.next_check_enable.setChecked(False)
            self.next_checks_edit.setEnabled(False)
            self.next_checks_edit.setText("")
 
        self._clear_rows()
        if not self._model.signals:
            self._model.signals = [SetSignalModel(kind="sys", name="", value="")]
 
        # 关键修复点：这里必须传 s（不要传 ok / self._parsed_ok）
        for s in self._model.signals:
            self._add_row(s)

    def _collect_model(self) -> SetStepModel:
        signals: List[SetSignalModel] = []
        for i in range(self.sig_layout.count()):
            w = self.sig_layout.itemAt(i).widget()
            if isinstance(w, SetSignalRow):
                signals.append(w.get_data())

        wait_ms = int(self.wait_spin.value())

        next_checks: List[str] = []
        if self.next_check_enable.isChecked():
            part = self.next_checks_edit.text().strip()
            if part:
                ids = [x.strip() for x in part.split(",") if x.strip()]
                next_checks = ids

        # 至少保留 1 条 signal，避免生成空
        if not signals:
            signals = [SetSignalModel(kind="sys", name="", value="")]

        return SetStepModel(signals=signals, wait_ms=wait_ms, next_checks=next_checks)

    def _on_ok(self) -> None:
        # 基础校验（尽量不阻塞）
        model = self._collect_model()
        # then check 的引用：如果提供了 available_check_ids，则做提示
        if model.next_checks and self._available_check_ids:
            bad = [c for c in model.next_checks if c not in self._available_check_ids]
            if bad:
                ret = QMessageBox.warning(
                    self,
                    "提示",
                    f"以下 CHECK 步骤在当前 CHECK 模块中不存在：{', '.join(bad)}\n仍然要保存吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return

        self._model = model
        self.accept()

    def to_dsl(self) -> str:
        return render_set_step(self._model)


# ----------------------------
# Step 编辑弹窗：CHECK
# ----------------------------
class CheckItemRow(QWidget):
    removed = pyqtSignal(object)
    KIND_WIDTH = 88
    MODE_WIDTH = 96
    OP_WIDTH = 90
    VALUE_WIDTH = 230
    RANGE_WIDTH = 110
    SPIN_WIDTH = 126
    ASYNC_WIDTH = 96
 
    def __init__(
        self,
        completions_by_kind: Dict[str, List[str]],
        hier_index_by_kind: Dict[str, Dict[Tuple[str, ...], List[str]]],
        parent=None,
        dbc_parser=None,
    ):
        super().__init__(parent)
        self._completions_by_kind = completions_by_kind
        self._hier_index_by_kind = hier_index_by_kind
        self._dbc_parser = dbc_parser
        self._build_ui()
 
    def _build_ui(self) -> None:
        self.setObjectName("checkItemRowCard")
        self.setStyleSheet(
            """
            QWidget#checkItemRowCard {
                background-color: #ffffff;
                border: 1px solid #d8e0ea;
                border-radius: 8px;
            }
            QWidget#checkItemRowCard QLineEdit,
            QWidget#checkItemRowCard QComboBox,
            QWidget#checkItemRowCard QSpinBox {
                background: #fbfcfe;
                border: 1px solid #cad5e3;
                border-radius: 4px;
                padding: 2px 8px;
            }
            QWidget#checkItemRowCard QLineEdit:focus,
            QWidget#checkItemRowCard QComboBox:focus,
            QWidget#checkItemRowCard QSpinBox:focus {
                border: 1px solid #5b9cff;
                background: #ffffff;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
 
        row1 = QWidget(self)
        l1 = QHBoxLayout(row1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(8)
 
        self.kind_label = QLabel("类型", row1)
        self.kind_label.setFixedWidth(34)
        self.kind_combo = QComboBox(row1)
        self.kind_combo.addItems(["sig", "env", "sys"])
        self.kind_combo.setFixedWidth(self.KIND_WIDTH)
        l1.addWidget(self.kind_label)
        l1.addWidget(self.kind_combo)
 
        self.name_label = QLabel("名称", row1)
        self.name_label.setFixedWidth(34)
        self.name_edit = QLineEdit(row1)
        self.name_edit.setPlaceholderText("信号名称（支持逐级补全）")
        l1.addWidget(self.name_label)
        l1.addWidget(self.name_edit, 1)
 
        btn_del = QPushButton("删除该检查项", row1)
        btn_del.setMinimumWidth(110)
        btn_del.setStyleSheet(
            """
            QPushButton {
                background: #ffefef;
                border: 1px solid #f0b9b9;
                border-radius: 4px;
                color: #b42318;
                font-weight: bold;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background: #ffe3e3;
                border-color: #e19d9d;
            }
            """
        )
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        l1.addWidget(btn_del)
 
        root.addWidget(row1)
 
        row2 = QWidget(self)
        l2 = QHBoxLayout(row2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(8)
 
        self.mode_label = QLabel("值模式", row2)
        self.mode_label.setFixedWidth(42)
        self.mode_combo = QComboBox(row2)
        self.mode_combo.addItems(["single", "list", "range"])
        self.mode_combo.setFixedWidth(self.MODE_WIDTH)
        l2.addWidget(self.mode_label)
        l2.addWidget(self.mode_combo)
 
        self.op_label = QLabel("比较符", row2)
        self.op_label.setFixedWidth(40)
        self.op_combo = QComboBox(row2)
        self.op_combo.addItems(["==", ">", "<", ">=", "<=", "="])
        self.op_combo.setFixedWidth(self.OP_WIDTH)
        l2.addWidget(self.op_label)
        l2.addWidget(self.op_combo)
 
        self.single_edit = QLineEdit(row2)
        self.single_edit.setPlaceholderText("单值，例如 3 / 0x1 / true")
        self.single_edit.setMinimumWidth(self.VALUE_WIDTH)
        l2.addWidget(self.single_edit, 1)
 
        self.list_edit = QLineEdit(row2)
        self.list_edit.setPlaceholderText("列表：用逗号分隔，例如 1,2,3")
        self.list_edit.setMinimumWidth(self.VALUE_WIDTH)
        l2.addWidget(self.list_edit, 1)
        self.list_edit.hide()
 
        self.range_a_edit = QLineEdit(row2)
        self.range_a_edit.setPlaceholderText("a")
        self.range_a_edit.setFixedWidth(self.RANGE_WIDTH)
        self.range_b_edit = QLineEdit(row2)
        self.range_b_edit.setPlaceholderText("b")
        self.range_b_edit.setFixedWidth(self.RANGE_WIDTH)
        l2.addWidget(self.range_a_edit)
        self.range_sep = QLabel("..", row2)
        self.range_sep.setFixedWidth(14)
        self.range_sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l2.addWidget(self.range_sep)
        l2.addWidget(self.range_b_edit)
        self.range_a_edit.hide()
        self.range_sep.hide()
        self.range_b_edit.hide()
 
        _set_uniform_height(
            self.mode_combo,
            self.op_combo,
            self.single_edit,
            self.list_edit,
            self.range_a_edit,
            self.range_b_edit,
        )

        root.addWidget(row2)
 
        row3 = QWidget(self)
        l3 = QHBoxLayout(row3)
        l3.setContentsMargins(0, 0, 0, 0)
        l3.setSpacing(8)
 
        self.wait_label = QLabel("wait", row3)
        self.wait_label.setFixedWidth(28)
        self.wait_spin = QSpinBox(row3)
        self.wait_spin.setRange(0, 10_000_000)
        self.wait_spin.setSuffix(" ms")
        self.wait_spin.setFixedWidth(self.SPIN_WIDTH)
        l3.addWidget(self.wait_label)
        l3.addWidget(self.wait_spin)
 
        self.timeout_label = QLabel("timeout", row3)
        self.timeout_label.setFixedWidth(48)
        self.timeout_spin = QSpinBox(row3)
        self.timeout_spin.setRange(0, 10_000_000)
        self.timeout_spin.setValue(1000)
        self.timeout_spin.setSuffix(" ms")
        self.timeout_spin.setFixedWidth(self.SPIN_WIDTH)
        l3.addWidget(self.timeout_label)
        l3.addWidget(self.timeout_spin)
 
        self.duration_label = QLabel("duration", row3)
        self.duration_label.setFixedWidth(50)
        self.duration_spin = QSpinBox(row3)
        self.duration_spin.setRange(0, 10_000_000)
        self.duration_spin.setSuffix(" ms（0 表示不输出）")
        self.duration_spin.setFixedWidth(self.SPIN_WIDTH + 20)
        l3.addWidget(self.duration_label)
        l3.addWidget(self.duration_spin)
 
        self.async_label = QLabel("async", row3)
        self.async_label.setFixedWidth(36)
        self.async_combo = QComboBox(row3)
        self.async_combo.addItems(["false", "true"])
        self.async_combo.setFixedWidth(self.ASYNC_WIDTH)
        l3.addWidget(self.async_label)
        l3.addWidget(self.async_combo)

        l3.addStretch(1)

        _set_uniform_height(
            self.kind_combo,
            self.name_edit,
            btn_del,
            self.wait_spin,
            self.timeout_spin,
            self.duration_spin,
            self.async_combo,
        )
 
        root.addWidget(row3)
 
        # 逐级补全（只对 name_edit）
        try:
            self._hier = _HierLineEditCompleter(
                edit=self.name_edit,
                kind_getter=lambda: self.kind_combo.currentText(),
                index_by_kind=self._hier_index_by_kind,
                allowed_kinds=["sig", "env", "sys"],
                dbc_parser=self._dbc_parser,
            )
        except TypeError:
            self._hier = _HierLineEditCompleter(
                edit=self.name_edit,
                kind_getter=lambda: self.kind_combo.currentText(),
                index_by_kind=self._hier_index_by_kind,
                allowed_kinds=["sig", "env", "sys"],
            )
        self.kind_combo.currentTextChanged.connect(lambda _k: self._hier.refresh())
 
        # mode/async 联动
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.async_combo.currentTextChanged.connect(self._on_async_changed)
        self._on_mode_changed(self.mode_combo.currentText())
        self._on_async_changed(self.async_combo.currentText())
 
    def _on_mode_changed(self, mode: str) -> None:
        mode = (mode or "single").lower()
        is_single = mode == "single"
        is_list = mode == "list"
        is_range = mode == "range"

        # single: 显示比较符 + 单值
        self.op_label.setVisible(is_single)
        self.op_combo.setVisible(is_single)
        self.single_edit.setVisible(is_single)

        # list: 仅显示列表输入
        self.list_edit.setVisible(is_list)

        # range: 显示 a .. b（含分隔符）
        self.range_a_edit.setVisible(is_range)
        self.range_sep.setVisible(is_range)
        self.range_b_edit.setVisible(is_range)
 
    def _on_async_changed(self, v: str) -> None:
        async_true = (v or "").strip().lower() == "true"
        if async_true:
            self.wait_spin.setValue(0)
        self.wait_spin.setEnabled(not async_true)
 
    def set_data(self, it: CheckItemModel) -> None:
        self.kind_combo.setCurrentText(it.kind if it.kind in ("sig", "env", "sys") else "sig")
        self.name_edit.setText(it.name or "")
 
        self.mode_combo.setCurrentText(it.mode if it.mode in ("single", "list", "range") else "single")
        self.op_combo.setCurrentText(it.op if it.op in ("==", ">", "<", ">=", "<=", "=") else "==")
 
        self.single_edit.setText(it.single_value or "")
        self.list_edit.setText(",".join(it.list_values or []))
        self.range_a_edit.setText(it.range_a or "")
        self.range_b_edit.setText(it.range_b or "")
 
        self.wait_spin.setValue(int(it.wait_ms or 0))
        self.timeout_spin.setValue(int(it.timeout_ms or 1000))
        self.duration_spin.setValue(int(it.duration_ms or 0))
        self.async_combo.setCurrentText("true" if it.async_ else "false")
        self._on_async_changed(self.async_combo.currentText())
        self._on_mode_changed(self.mode_combo.currentText())
        self._hier.refresh()
 
    def get_data(self) -> CheckItemModel:
        kind = self.kind_combo.currentText()
        name = self.name_edit.text().strip()
        mode = self.mode_combo.currentText()
 
        op = self.op_combo.currentText()
        single = self.single_edit.text().strip()
        lst = [x.strip() for x in self.list_edit.text().split(",") if x.strip()]
        ra = self.range_a_edit.text().strip()
        rb = self.range_b_edit.text().strip()
 
        async_ = self.async_combo.currentText().strip().lower() == "true"
        wait_ms = int(self.wait_spin.value()) if not async_ else 0
 
        return CheckItemModel(
            kind=kind,
            name=name,
            mode=mode,
            op=op,
            single_value=single,
            list_values=lst,
            range_a=ra,
            range_b=rb,
            wait_ms=wait_ms,
            timeout_ms=int(self.timeout_spin.value()),
            duration_ms=int(self.duration_spin.value()),
            async_=async_,
        )

class CheckStepDialog(QDialog):
    def __init__(self, raw_text: str, completions_by_kind: Dict[str, List[str]], parent=None, dbc_parser=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 CHECK Step")
        self.resize(980, 650)

        self._raw_text = raw_text or ""
        self._completions_by_kind = completions_by_kind
        self._hier_index_by_kind = _build_hier_index_by_kind(self._completions_by_kind)
        self._dbc_parser = dbc_parser

        self._model = CheckStepModel(items=[CheckItemModel(kind="sig", name="", mode="single")])
        self._parsed_ok = False
        self._parse_msg = ""

        self._build_ui()
        self._try_parse_and_fill()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.tip = QLabel("", self)
        self.tip.setStyleSheet("color: #b00020;")
        self.tip.setWordWrap(True)
        layout.addWidget(self.tip)

        items_box = QGroupBox("CHECK 信号列表", self)
        _setup_groupbox_style(items_box)
        items_l = QVBoxLayout(items_box)

        header = QWidget(items_box)
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(6)
        info = QLabel("每条独立 timeout/duration/async/wait；async=true 时 wait 置灰", items_box)
        info.setStyleSheet("color: #666666;")
        info.setWordWrap(True)
        btn_add = QPushButton("添加检查项", items_box)
        btn_add.clicked.connect(self._add_row)
        header_l.addWidget(info, 1)
        header_l.addWidget(btn_add)
        items_l.addWidget(header)

        self.items_scroll = QScrollArea(items_box)
        _setup_scroll(self.items_scroll)

        self.items_container = QWidget(self.items_scroll)
        self.items_container.setContentsMargins(0, 0, 0, 0)

        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(10)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.items_scroll.setWidget(self.items_container)
        items_l.addWidget(self.items_scroll, 1)

        layout.addWidget(items_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _set_tip(self, msg: str) -> None:
        self.tip.setText(msg or "")

    def _clear_rows(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_row(self, data: Optional[CheckItemModel] = None) -> None:
        row = CheckItemRow(
            self._completions_by_kind,
            self._hier_index_by_kind,
            parent=self.items_container,
            dbc_parser=self._dbc_parser,
        )
        row.removed.connect(self._remove_row)
    
        if isinstance(data, CheckItemModel):
            row.set_data(data)
    
        self.items_layout.addWidget(row)

    def _remove_row(self, row: CheckItemRow) -> None:
        if self.items_layout.count() <= 1:
            row.set_data(CheckItemModel(kind="sig", name="", mode="single"))
            return
        self.items_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _try_parse_and_fill(self) -> None:
        model, ok, msg = parse_check_step(self._raw_text)
        self._model = model
        self._parsed_ok = ok
        self._parse_msg = msg
 
        if not ok:
            self._set_tip("当前文本无法完全解析，将以表单内容重新生成并覆盖主界面文本。")
        else:
            self._set_tip("")
 
        self._clear_rows()
        if not self._model.items:
            self._model.items = [CheckItemModel(kind="sig", name="", mode="single")]
 
        # 关键修复点：这里必须传 it（不要传 ok / self._parsed_ok）
        for it in self._model.items:
            self._add_row(it)

    def _collect_model(self) -> CheckStepModel:
        items: List[CheckItemModel] = []
        for i in range(self.items_layout.count()):
            w = self.items_layout.itemAt(i).widget()
            if isinstance(w, CheckItemRow):
                items.append(w.get_data())

        if not items:
            items = [CheckItemModel(kind="sig", name="", mode="single")]

        # timeout 默认 1000ms：若用户填 0，则自动补 1000
        for it in items:
            if int(it.timeout_ms or 0) <= 0:
                it.timeout_ms = 1000
            if it.async_:
                it.wait_ms = 0

        return CheckStepModel(items=items)

    def _on_ok(self) -> None:
        self._model = self._collect_model()
        self.accept()

    def to_dsl(self) -> str:
        return render_check_step(self._model)


# ----------------------------
# 主界面模块：CASE / META
# ----------------------------
class CaseInfoWidget(QWidget):
    """CASE信息模块"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        group = QGroupBox("CASE信息", self)
        _setup_groupbox_style(group)

        form_layout = QFormLayout(group)
        _align_form_layout(form_layout)

        self.case_name_edit = QLineEdit(group)
        self.case_name_edit.setPlaceholderText("输入CASE名称，如：OrinN_MR25_CSW_027_001")
        self.case_name_edit.setMinimumWidth(400)
        form_layout.addRow("CASE名称*:", self.case_name_edit)
        _fix_label_for_field(form_layout, self.case_name_edit)

        self.case_id_edit = QLineEdit(group)
        self.case_id_edit.setPlaceholderText("输入CASE ID")
        self.case_id_edit.setMinimumWidth(400)
        form_layout.addRow("CASE ID:", self.case_id_edit)
        _fix_label_for_field(form_layout, self.case_id_edit)

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
    """META信息模块"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        group = QGroupBox("META信息", self)
        _setup_groupbox_style(group)

        form_layout = QFormLayout(group)
        _align_form_layout(form_layout)

        self.test_point_edit = QLineEdit(group)
        self.test_point_edit.setPlaceholderText("输入测试点描述")
        form_layout.addRow("测试点*:", self.test_point_edit)
        _fix_label_for_field(form_layout, self.test_point_edit)

        self.priority_combo = QComboBox(group)
        self.priority_combo.addItems(["P0-高", "P1-中", "P2-低"])
        form_layout.addRow("优先级:", self.priority_combo)
        _fix_label_for_field(form_layout, self.priority_combo)

        self.owner_edit = QLineEdit(group)
        self.owner_edit.setPlaceholderText("输入负责人")
        form_layout.addRow("负责人:", self.owner_edit)
        _fix_label_for_field(form_layout, self.owner_edit)

        self.scenario_id_edit = QLineEdit(group)
        self.scenario_id_edit.setPlaceholderText("输入场景ID")
        form_layout.addRow("场景ID:", self.scenario_id_edit)
        _fix_label_for_field(form_layout, self.scenario_id_edit)

        self.scenario_name_edit = QLineEdit(group)
        self.scenario_name_edit.setPlaceholderText("输入场景名称")
        form_layout.addRow("场景名称:", self.scenario_name_edit)
        _fix_label_for_field(form_layout, self.scenario_name_edit)

        self.ai_analysis_checkbox = QCheckBox("启用AI分析", group)
        form_layout.addRow("", self.ai_analysis_checkbox)
        _fix_label_for_field(form_layout, self.ai_analysis_checkbox)

        self.record_checkbox = QCheckBox("启用记录", group)
        form_layout.addRow("", self.record_checkbox)
        _fix_label_for_field(form_layout, self.record_checkbox)

        layout.addWidget(group)
        layout.addStretch()

    def get_meta_info(self) -> Dict[str, Any]:
        return {
            "test_point": self.test_point_edit.text().strip(),
            "priority": self.priority_combo.currentText(),
            "owner": self.owner_edit.text().strip(),
            "scenario_id": self.scenario_id_edit.text().strip(),
            "scenario_name": self.scenario_name_edit.text().strip(),
            "ai_analysis": self.ai_analysis_checkbox.isChecked(),
            "record": self.record_checkbox.isChecked(),
        }

    def set_meta_info(self, meta_info: Dict[str, Any]) -> None:
        self.test_point_edit.setText(meta_info.get("test_point", ""))
        self.priority_combo.setCurrentText(meta_info.get("priority", "P1-中"))
        self.owner_edit.setText(meta_info.get("owner", ""))
        self.scenario_id_edit.setText(meta_info.get("scenario_id", ""))
        self.scenario_name_edit.setText(meta_info.get("scenario_name", ""))
        self.ai_analysis_checkbox.setChecked(bool(meta_info.get("ai_analysis", False)))
        self.record_checkbox.setChecked(bool(meta_info.get("record", False)))

    def clear(self) -> None:
        self.test_point_edit.clear()
        self.priority_combo.setCurrentIndex(1)
        self.owner_edit.clear()
        self.scenario_id_edit.clear()
        self.scenario_name_edit.clear()
        self.ai_analysis_checkbox.setChecked(False)
        self.record_checkbox.setChecked(False)


# ----------------------------
# 主界面 Step 行（只读）
# ----------------------------
class StepWidget(QWidget):
    add_requested = pyqtSignal(object)     # self
    delete_requested = pyqtSignal(object)  # self
    edit_requested = pyqtSignal(object)    # self

    def __init__(self, step_id: str, step_type: str = "SET", parent=None):
        super().__init__(parent)
        self.step_id = step_id
        self.step_type = step_type
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(FORM_HSPACING)

        self.id_label = QLabel(f"{self.step_id}:", row)
        self.id_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.id_label.setStyleSheet("color: #569CD6;")
        self.id_label.setFixedWidth(FORM_LABEL_WIDTH)
        self.id_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        content_container = QWidget(row)
        content_layout = QHBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        self.content_edit = QLineEdit(content_container)
        if self.step_type == "SET":
            self.content_edit.setPlaceholderText("set sys::FunctionSwitch::CSW_Enable_S=0x1 wait 500ms then check C1")
        else:
            self.content_edit.setPlaceholderText(
                "check sig::CAN 1::ADC_0x29C::CSW_Stats_S==3 timeout 1000ms async false"
            )
        self.content_edit.setMinimumWidth(520)
        self.content_edit.setReadOnly(True)
        self.content_edit.setStyleSheet(
            """
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 5px;
                background-color: #f7f7f7;
            }
            QLineEdit:read-only {
                color: #333333;
            }
            """
        )
        content_layout.addWidget(self.content_edit, 1)

        btn_edit = QPushButton("编辑", content_container)
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self))
        content_layout.addWidget(btn_edit)

        btn_add = QPushButton("+", content_container)
        btn_add.setMaximumWidth(40)
        btn_add.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
            """
        )
        btn_add.clicked.connect(lambda: self.add_requested.emit(self))
        content_layout.addWidget(btn_add)

        btn_del = QPushButton("-", content_container)
        btn_del.setMaximumWidth(40)
        btn_del.setStyleSheet(
            """
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff5252; }
            """
        )
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self))
        content_layout.addWidget(btn_del)

        row_layout.addWidget(self.id_label)
        row_layout.addWidget(content_container, 1)
        root.addWidget(row)

    def set_step_id(self, new_id: str) -> None:
        self.step_id = new_id
        self.id_label.setText(f"{new_id}:")

    def get_step_content(self) -> str:
        return self.content_edit.text().strip()

    def set_step_content(self, content: Any) -> None:
        if content is None or content is False:
            content = ""
        elif not isinstance(content, str):
            content = str(content)
        self.content_edit.setText(content)


# ----------------------------
# SET 模块（顺序/删除稳定 + 弹窗编辑）
# ----------------------------
class SetModuleWidget(QWidget):
    steps_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: List[StepWidget] = []
        self.completions: List[str] = []
        self.get_check_ids_provider = None  # type: ignore[assignment]
        self._build_ui()
        self.add_step(after_step=None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        group = QGroupBox("SET模块", self)
        _setup_groupbox_style(group)

        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)

        scroll = QScrollArea(group)
        _setup_scroll(scroll)

        self.steps_container = QWidget(scroll)
        self.steps_container.setContentsMargins(0, 0, 0, 0)

        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(6)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.steps_container)
        group_layout.addWidget(scroll)
        layout.addWidget(group)

    def set_completions(self, completions: List[str]) -> None:
        self.completions = completions

    def _completions_by_kind(self) -> Dict[str, List[str]]:
        sys_list = [c for c in self.completions if c.startswith("sys::")]
        env_list = [c for c in self.completions if c.startswith("env::")]
        sig_list = [c for c in self.completions if c.startswith("sig::")]
        return {"sys": sys_list, "env": env_list, "sig": sig_list}

    def add_step(self, content: Any = "", after_step: Optional[StepWidget] = None) -> None:
        step = StepWidget("S?", "SET", self.steps_container)
        step.set_step_content(content)

        step.add_requested.connect(self._on_add_requested)
        step.delete_requested.connect(self._on_delete_requested)
        step.edit_requested.connect(self._on_edit_requested)

        if after_step is not None and after_step in self.steps:
            idx = self.steps.index(after_step) + 1
            self.steps.insert(idx, step)
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
        raw = step.get_step_content()
        check_ids: List[str] = []
        if callable(self.get_check_ids_provider):
            try:
                check_ids = list(self.get_check_ids_provider())
            except Exception:
                check_ids = []
 
        dlg = SetStepDialog(
            raw_text=raw,
            completions_by_kind={"sys": self._completions_by_kind()["sys"], "env": self._completions_by_kind()["env"]},
            available_check_ids=check_ids,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            step.set_step_content(dlg.to_dsl())
            self.steps_changed.emit()

    def remove_step(self, step: StepWidget) -> None:
        if step not in self.steps:
            return
        if len(self.steps) <= 1:
            step.set_step_content("")
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
            w = item.widget()
            if w is not None:
                self.steps_layout.removeWidget(w)
        for s in self.steps:
            self.steps_layout.addWidget(s)

    def _renumber_steps(self) -> None:
        for i, s in enumerate(self.steps, start=1):
            s.set_step_id(f"S{i}")

    def apply_check_id_mapping(self, mapping: Dict[str, str]) -> None:
        if not mapping:
            return

        # 支持 then check C1 / then check C1,C2 / then check C1, C2
        pat = re.compile(r"(then\s+check\s+)(C\d+(?:\s*,\s*C\d+)*)", re.IGNORECASE)

        for step in self.steps:
            text = step.get_step_content()
            if not text:
                continue

            def repl(m: re.Match) -> str:
                head = m.group(1)
                ids_part = m.group(2)
                ids = [x.strip() for x in ids_part.split(",") if x.strip()]
                ids2 = [mapping.get(x, x) for x in ids]
                return head + ",".join(ids2)

            new_text = pat.sub(repl, text)
            if new_text != text:
                step.set_step_content(new_text)

    def get_steps(self) -> List[Dict[str, str]]:
        return [{"id": s.step_id, "content": s.get_step_content()} for s in self.steps]

    def set_steps(self, steps: List[Dict[str, Any]]) -> None:
        for s in self.steps:
            self.steps_layout.removeWidget(s)
            s.setParent(None)
            s.deleteLater()
        self.steps.clear()

        for step_data in steps:
            self.add_step(content=step_data.get("content", ""), after_step=self.steps[-1] if self.steps else None)

        if not self.steps:
            self.add_step(after_step=None)

    def clear(self) -> None:
        for s in self.steps[1:]:
            self.steps_layout.removeWidget(s)
            s.setParent(None)
            s.deleteLater()

        if self.steps:
            self.steps[0].set_step_content("")
            self.steps = [self.steps[0]]
            self._rebuild_layout()
            self._renumber_steps()
            self.steps_changed.emit()
        else:
            self.add_step(after_step=None)


# ----------------------------
# CHECK 模块（顺序/删除稳定 + 弹窗编辑）
# ----------------------------
class CheckModuleWidget(QWidget):
    steps_changed = pyqtSignal()
    check_id_mapping_emitted = pyqtSignal(dict)  # old->new

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: List[StepWidget] = []
        self.completions: List[str] = []
        self._build_ui()
        self.add_step(after_step=None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        group = QGroupBox("CHECK模块", self)
        _setup_groupbox_style(group)

        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)

        scroll = QScrollArea(group)
        _setup_scroll(scroll)

        self.steps_container = QWidget(scroll)
        self.steps_container.setContentsMargins(0, 0, 0, 0)

        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(6)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.steps_container)
        group_layout.addWidget(scroll)
        layout.addWidget(group)

    def set_completions(self, completions: List[str]) -> None:
        self.completions = completions

    def _completions_by_kind(self) -> Dict[str, List[str]]:
        sys_list = [c for c in self.completions if c.startswith("sys::")]
        env_list = [c for c in self.completions if c.startswith("env::")]
        sig_list = [c for c in self.completions if c.startswith("sig::")]
        return {"sys": sys_list, "env": env_list, "sig": sig_list}

    def add_step(self, content: Any = "", after_step: Optional[StepWidget] = None) -> None:
        step = StepWidget("C?", "CHECK", self.steps_container)
        step.set_step_content(content)

        step.add_requested.connect(self._on_add_requested)
        step.delete_requested.connect(self._on_delete_requested)
        step.edit_requested.connect(self._on_edit_requested)

        if after_step is not None and after_step in self.steps:
            idx = self.steps.index(after_step) + 1
            self.steps.insert(idx, step)
        else:
            self.steps.append(step)

        self._rebuild_layout()
        mapping = self._renumber_steps_and_get_mapping()
        self.steps_changed.emit()
        if mapping:
            self.check_id_mapping_emitted.emit(mapping)

    def _on_add_requested(self, step: StepWidget) -> None:
        self.add_step(after_step=step)

    def _on_delete_requested(self, step: StepWidget) -> None:
        self.remove_step(step)

    def _on_edit_requested(self, step: StepWidget) -> None:
        raw = step.get_step_content()
        dlg = CheckStepDialog(raw_text=raw, completions_by_kind=self._completions_by_kind(), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            step.set_step_content(dlg.to_dsl())
            self.steps_changed.emit()

    def remove_step(self, step: StepWidget) -> None:
        if step not in self.steps:
            return
        if len(self.steps) <= 1:
            step.set_step_content("")
            return

        self.steps.remove(step)
        self.steps_layout.removeWidget(step)
        step.setParent(None)
        step.deleteLater()

        self._rebuild_layout()
        mapping = self._renumber_steps_and_get_mapping()
        self.steps_changed.emit()
        if mapping:
            self.check_id_mapping_emitted.emit(mapping)

    def _rebuild_layout(self) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                self.steps_layout.removeWidget(w)
        for s in self.steps:
            self.steps_layout.addWidget(s)

    def _renumber_steps_and_get_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for i, s in enumerate(self.steps, start=1):
            new_id = f"C{i}"
            if s.step_id != new_id and s.step_id not in ("C?", ""):
                mapping[s.step_id] = new_id
            s.set_step_id(new_id)
        return {k: v for k, v in mapping.items() if k != v}

    def get_steps(self) -> List[Dict[str, str]]:
        return [{"id": s.step_id, "content": s.get_step_content()} for s in self.steps]

    def set_steps(self, steps: List[Dict[str, Any]]) -> None:
        for s in self.steps:
            self.steps_layout.removeWidget(s)
            s.setParent(None)
            s.deleteLater()
        self.steps.clear()

        for step_data in steps:
            self.add_step(content=step_data.get("content", ""), after_step=self.steps[-1] if self.steps else None)

        if not self.steps:
            self.add_step(after_step=None)

    def clear(self) -> None:
        for s in self.steps[1:]:
            self.steps_layout.removeWidget(s)
            s.setParent(None)
            s.deleteLater()

        if self.steps:
            self.steps[0].set_step_content("")
            self.steps = [self.steps[0]]
            self._rebuild_layout()
            self._renumber_steps_and_get_mapping()
            self.steps_changed.emit()
        else:
            self.add_step(after_step=None)


# ----------------------------
# 顶层编辑器：组合模块 + 导入导出 DSL
# ----------------------------
class ModularCaseEditor(QWidget):
    content_changed = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.completions: List[str] = []
        self._build_ui()
        self._wire_signals()

    def _emit_content_changed(self, *_args) -> None:
        sig = getattr(self, "content_changed", None)
        if sig is not None:
            sig.emit()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        _setup_scroll(scroll)

        container = QWidget(scroll)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        self.case_info_widget = CaseInfoWidget(container)
        container_layout.addWidget(self.case_info_widget)

        self.meta_info_widget = MetaInfoWidget(container)
        container_layout.addWidget(self.meta_info_widget)

        self.set_module_widget = SetModuleWidget(container)
        container_layout.addWidget(self.set_module_widget)

        self.check_module_widget = CheckModuleWidget(container)
        container_layout.addWidget(self.check_module_widget)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _wire_signals(self) -> None:
        self.check_module_widget.check_id_mapping_emitted.connect(self.set_module_widget.apply_check_id_mapping)
        self.set_module_widget.get_check_ids_provider = lambda: [s.step_id for s in self.check_module_widget.steps]
 
        # 任意变化 -> 标记内容已变更
        self.case_info_widget.case_name_edit.textChanged.connect(self._emit_content_changed)
        self.case_info_widget.case_id_edit.textChanged.connect(self._emit_content_changed)
 
        self.meta_info_widget.test_point_edit.textChanged.connect(self._emit_content_changed)
        self.meta_info_widget.priority_combo.currentTextChanged.connect(self._emit_content_changed)
        self.meta_info_widget.owner_edit.textChanged.connect(self._emit_content_changed)
        self.meta_info_widget.scenario_id_edit.textChanged.connect(self._emit_content_changed)
        self.meta_info_widget.scenario_name_edit.textChanged.connect(self._emit_content_changed)
        self.meta_info_widget.ai_analysis_checkbox.toggled.connect(self._emit_content_changed)
        self.meta_info_widget.record_checkbox.toggled.connect(self._emit_content_changed)
 
        self.set_module_widget.steps_changed.connect(self._emit_content_changed)
        self.check_module_widget.steps_changed.connect(self._emit_content_changed)

    def set_completions(self, completions: List[str]) -> None:
        self.completions = completions
        self.set_module_widget.set_completions(completions)
        self.check_module_widget.set_completions(completions)
 
    # 给 MainWindow 的编辑菜单用：把操作派发给当前焦点控件
    def _dispatch_to_focused(self, method_name: str) -> None:
        w = QApplication.focusWidget()
        if w is None:
            return
        if not self.isAncestorOf(w) and w is not self:
            return
        fn = getattr(w, method_name, None)
        if callable(fn):
            fn()
 
    def undo(self) -> None:
        self._dispatch_to_focused("undo")
 
    def redo(self) -> None:
        self._dispatch_to_focused("redo")
 
    def cut(self) -> None:
        self._dispatch_to_focused("cut")
 
    def copy(self) -> None:
        self._dispatch_to_focused("copy")
 
    def paste(self) -> None:
        self._dispatch_to_focused("paste")
 
    def selectAll(self) -> None:
        self._dispatch_to_focused("selectAll")

    def get_case_data(self) -> Dict[str, Any]:
        return {
            "case_info": self.case_info_widget.get_case_info(),
            "meta_info": self.meta_info_widget.get_meta_info(),
            "set_steps": self.set_module_widget.get_steps(),
            "check_steps": self.check_module_widget.get_steps(),
        }

    def set_case_data(self, case_data: Dict[str, Any]) -> None:
        self.case_info_widget.set_case_info(
            case_data.get("case_info", {}).get("name", ""),
            case_data.get("case_info", {}).get("id", ""),
        )
        self.meta_info_widget.set_meta_info(case_data.get("meta_info", {}))
        self.set_module_widget.set_steps(case_data.get("set_steps", []))
        self.check_module_widget.set_steps(case_data.get("check_steps", []))

    def to_dsl(self) -> str:
        data = self.get_case_data()
        dsl_lines: List[str] = []

        case_info = data["case_info"]
        if case_info.get("name"):
            dsl_lines.append(f"CASE: {case_info['name']}")

        meta_info = data["meta_info"]
        meta_parts: List[str] = []
        if meta_info.get("test_point"):
            meta_parts.append(f"test_point={meta_info['test_point']}")
        if meta_info.get("priority"):
            meta_parts.append(f"priority={meta_info['priority']}")
        if meta_info.get("owner"):
            meta_parts.append(f"owner={meta_info['owner']}")
        if meta_info.get("scenario_id"):
            meta_parts.append(f"scenario_id={meta_info['scenario_id']}")
        if meta_info.get("scenario_name"):
            meta_parts.append(f"scenario_name={meta_info['scenario_name']}")
        if meta_info.get("ai_analysis"):
            meta_parts.append(f"ai_analysis={meta_info['ai_analysis']}")
        if meta_info.get("record"):
            meta_parts.append(f"record={meta_info['record']}")
        if meta_parts:
            dsl_lines.append("META: " + " ".join(meta_parts))

        dsl_lines.append("")
        dsl_lines.append("[SET]")
        for step in data["set_steps"]:
            dsl_lines.append(f"{step['id']}: {step['content']}")

        dsl_lines.append("")
        dsl_lines.append("[CHECK]")
        for step in data["check_steps"]:
            dsl_lines.append(f"{step['id']}: {step['content']}")

        return "\n".join(dsl_lines)

    def from_dsl(self, dsl_content: str) -> None:
        data = {"case_info": {"name": "", "id": ""}, "meta_info": {}, "set_steps": [], "check_steps": []}
        lines = (dsl_content or "").split("\n")
        current_section: Optional[str] = None

        for raw in lines:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("CASE:"):
                data["case_info"]["name"] = line[5:].strip()
                continue

            if line.startswith("META:"):
                meta_str = line[5:].strip()
                for pair in meta_str.split():
                    if "=" not in pair:
                        continue
                    k, v = pair.split("=", 1)
                    if k in ("ai_analysis", "record"):
                        data["meta_info"][k] = v.lower() in ("true", "1", "yes")
                    else:
                        data["meta_info"][k] = v
                continue

            if line == "[SET]":
                current_section = "SET"
                continue

            if line == "[CHECK]":
                current_section = "CHECK"
                continue

            m = re.match(r"^([SC]\d+):\s*(.*)$", line)
            if not m:
                continue
            step_id = m.group(1)
            step_content = m.group(2).strip()

            if current_section == "SET":
                data["set_steps"].append({"id": step_id, "content": step_content})
            elif current_section == "CHECK":
                data["check_steps"].append({"id": step_id, "content": step_content})

        self.set_case_data(data)

    def validate(self) -> List[str]:
        errors: List[str] = []
        data = self.get_case_data()

        if not data["case_info"]["name"]:
            errors.append("CASE名称不能为空")
        if not data["meta_info"].get("test_point"):
            errors.append("测试点不能为空")
        if not data["set_steps"]:
            errors.append("至少需要一个SET步骤")
        if not data["check_steps"]:
            errors.append("至少需要一个CHECK步骤")

        # then check 引用校验（支持 C1 或 C1,C2）
        check_step_ids = {step["id"] for step in data["check_steps"]}
        pat = re.compile(r"then\s+check\s+([C]\d+(?:\s*,\s*[C]\d+)*)", re.IGNORECASE)

        for step in data["set_steps"]:
            m = pat.search(step.get("content") or "")
            if not m:
                continue
            ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
            for cid in ids:
                if cid not in check_step_ids:
                    errors.append(f"SET步骤 {step['id']} 引用的检查步骤 {cid} 不存在")

        return errors


# ----------------------------
# Demo 入口（可删除/集成到你的主程序）
# ----------------------------
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("ModularCaseEditor Demo")
    w.resize(1200, 800)

    layout = QVBoxLayout(w)
    editor = ModularCaseEditor(w)

    # 示例补全（你后续用 DBC/系统变量索引替换）
    editor.set_completions(
        [
            "sys::FunctionSwitch::CSW_Enable_S",
            "sys::DriverAction::gear",
            "env::CAN 1::IPB_0x10C::VDC_Active",
            "sig::CAN 1::ADC_0x29C::CSW_Stats_S",
            "sig::CAN 1::ADC_0x29C::DNP_warning_text_info",
        ]
    )

    layout.addWidget(editor, 1)

    btn_row = QHBoxLayout()
    btn_export = QPushButton("导出 DSL 到弹窗", w)
    btn_validate = QPushButton("校验", w)

    def _on_export():
        dsl = editor.to_dsl()
        dlg = QDialog(w)
        dlg.setWindowTitle("导出 DSL")
        dlg.resize(900, 600)
        l = QVBoxLayout(dlg)
        t = QTextEdit(dlg)
        t.setPlainText(dsl)
        l.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        bb.clicked.connect(lambda: dlg.accept())
        l.addWidget(bb)
        dlg.exec()

    def _on_validate():
        errs = editor.validate()
        if not errs:
            QMessageBox.information(w, "校验通过", "未发现问题。")
        else:
            QMessageBox.warning(w, "校验失败", "\n".join(errs))

    btn_export.clicked.connect(_on_export)
    btn_validate.clicked.connect(_on_validate)
    btn_row.addWidget(btn_export)
    btn_row.addWidget(btn_validate)
    btn_row.addStretch(1)
    layout.addLayout(btn_row)

    w.show()
    sys.exit(app.exec())
