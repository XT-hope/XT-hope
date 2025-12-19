#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将第一种 .dsl case 文本批量转换为第二种 .py case 脚本。

约定（按用户描述实现）：
- CASE: -> 生成 __name__
- META: -> 解析 key=value；若包含 scenario_id，则在 URLTests 开头插入 SetScenario
- Sx: set ... -> 生成一个 URLTests 条目，description 为 "Sx"
  - 支持 "&&" 一行内设置多个信号
  - 支持 keep_dynamic false / keepDynamic false：在本步骤最前插入 SetSysVar simulink.dynamic_disconnect=1
  - 支持 wait 500ms / wait 0.5s：在本步骤末尾追加 Wait（秒）
  - 支持 then CHECK C1,C2：在本步骤之后立刻插入对应 Cn 的检查步骤
- Cx: check ... -> 生成一个 URLTests 条目，description 为 "Cx"
  - 支持 timeoutOfCheck 1500ms/5s -> timeout（秒）
  - 支持 checkInTime 2s -> CheckDuration（duration 秒）
  - 支持 wait 200ms -> 在该 Check* action 内加入 wait_time（秒）（与用户示例一致）

注意：
- URLmapping 仅收集 env::... 与 sig::... 的 signal_name（不包含 sys 变量名）
- 对于 "in {2,3}" 和 "in 2..5" 条件，会额外写入 operator 字段，避免丢失语义
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_RE_CASE = re.compile(r"^\s*CASE\s*:\s*(?P<name>.+?)\s*$")
_RE_META = re.compile(r"^\s*META\s*:\s*(?P<meta>.+?)\s*$")
_RE_SECTION = re.compile(r"^\s*\[(?P<section>[A-Za-z_]+)\]\s*$")
_RE_S = re.compile(r"^\s*(?P<label>S\d+)\s*:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
_RE_C = re.compile(r"^\s*(?P<label>C\d+)\s*:\s*(?P<body>.+?)\s*$", re.IGNORECASE)

_RE_WAIT = re.compile(r"\bwait\s+(?P<t>[0-9]+(?:\.[0-9]+)?)(?P<unit>ms|s)\b", re.IGNORECASE)
_RE_KEEP_DYN_FALSE = re.compile(r"\bkeep(?:_dynamic|Dynamic)?\s+false\b", re.IGNORECASE)
_RE_THEN_CHECK = re.compile(r"\bthen\s+CHECK\s+(?P<refs>.+?)\s*$", re.IGNORECASE)

_RE_TIMEOUT = re.compile(r"\btimeoutOfCheck\s+(?P<t>[0-9]+(?:\.[0-9]+)?)(?P<unit>ms|s)\b", re.IGNORECASE)
_RE_CHECK_IN_TIME = re.compile(r"\bcheckInTime\s+(?P<t>[0-9]+(?:\.[0-9]+)?)(?P<unit>ms|s)\b", re.IGNORECASE)

_RE_SYS = re.compile(r"^\s*sys::(?P<ns>[A-Za-z0-9_]+)::(?P<var>[A-Za-z0-9_]+)\s*$")
_RE_ENV_CAN = re.compile(
    r"^\s*env::CAN\s+(?P<ch>\d+)\s*::(?P<msg>[A-Za-z0-9_]+)::(?P<sig>[A-Za-z0-9_]+)\s*$",
    re.IGNORECASE,
)
_RE_SIG_CAN = re.compile(
    r"^\s*sig::CAN\s+(?P<ch>\d+)\s*::(?P<msg>[A-Za-z0-9_]+)::(?P<sig>[A-Za-z0-9_]+)\s*$",
    re.IGNORECASE,
)


def _time_to_seconds(num: str, unit: str) -> float:
    v = float(num)
    u = unit.lower()
    if u == "ms":
        return v / 1000.0
    if u == "s":
        return v
    raise ValueError(f"不支持的时间单位: {unit}")


def _parse_scalar(token: str) -> Any:
    t = token.strip()
    if not t:
        return t
    # hex
    if re.fullmatch(r"0x[0-9a-fA-F]+", t):
        return int(t, 16)
    # int
    if re.fullmatch(r"[+-]?\d+", t):
        return int(t)
    # float
    if re.fullmatch(r"[+-]?\d+\.\d+", t):
        return float(t)
    return t


def _strip_trailing_punct(s: str) -> str:
    return s.strip().rstrip(".").rstrip(",").strip()


def _parse_meta_kv(meta_str: str) -> Dict[str, str]:
    # META 中通常以空格分隔 key=value；值里一般不含空格（按用户示例）
    out: Dict[str, str] = {}
    for part in meta_str.strip().split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


@dataclass(frozen=True)
class DslSetStep:
    label: str
    raw: str
    keep_dynamic_false: bool
    wait_seconds: Optional[float]
    then_checks: Tuple[str, ...]
    ops: Tuple[Tuple[str, str, Any], ...]
    # op tuple: (kind, name_or_ns, value)
    # kind == "env": name_or_ns is signal_name
    # kind == "sys": name_or_ns is "namespace::var"


@dataclass(frozen=True)
class DslCheckStep:
    label: str
    raw: str
    signal_name: str
    predicate: Dict[str, Any]  # {"type": "eq"/"in"/"range", ...}
    timeout_seconds: Optional[float]
    duration_seconds: Optional[float]
    wait_seconds: Optional[float]


@dataclass(frozen=True)
class DslCase:
    name: str
    meta: Dict[str, str]
    set_steps: Tuple[DslSetStep, ...]
    check_steps: Tuple[DslCheckStep, ...]


def _extract_wait_seconds(text: str) -> Tuple[str, Optional[float]]:
    m = _RE_WAIT.search(text)
    if not m:
        return text, None
    seconds = _time_to_seconds(m.group("t"), m.group("unit"))
    # 去掉第一个 wait 段
    new_text = (text[: m.start()] + text[m.end() :]).strip()
    return new_text, seconds


def _extract_keep_dynamic_false(text: str) -> Tuple[str, bool]:
    m = _RE_KEEP_DYN_FALSE.search(text)
    if not m:
        return text, False
    new_text = (text[: m.start()] + text[m.end() :]).strip()
    return new_text, True


def _extract_then_checks(text: str) -> Tuple[str, Tuple[str, ...]]:
    m = _RE_THEN_CHECK.search(text)
    if not m:
        return text, ()
    refs = m.group("refs")
    # 只保留类似 C1/C2 的引用
    labels: List[str] = []
    for piece in re.split(r"[,\s]+", refs.strip()):
        p = _strip_trailing_punct(piece)
        if re.fullmatch(r"C\d+", p, flags=re.IGNORECASE):
            labels.append(p.upper())
    new_text = text[: m.start()].strip()
    return new_text, tuple(labels)


def _split_set_ops(text: str) -> List[str]:
    # 支持 "&&" 链式设置（两侧空格不定）
    parts = [p.strip() for p in re.split(r"\s*&&\s*", text) if p.strip()]
    return parts


def _parse_set_op(op_text: str) -> Tuple[str, str, Any, Optional[str]]:
    """
    returns (kind, name, value, urlmapping_signal_name_or_none)
    """
    t = op_text.strip()
    if t.lower().startswith("set "):
        t = t[4:].strip()

    if "=" in t:
        lhs, rhs = t.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        value = _parse_scalar(rhs)
    else:
        lhs = t.strip()
        value = 1  # 未显式给值时，默认置 1（尽量保持可用）

    m_sys = _RE_SYS.match(lhs)
    if m_sys:
        ns = m_sys.group("ns")
        var = m_sys.group("var")
        return ("sys", f"{ns}::{var}", value, None)

    m_env = _RE_ENV_CAN.match(lhs)
    if m_env:
        sig = m_env.group("sig")
        return ("env", sig, value, sig)

    # 兜底：取最后一个 :: 后的名称作为 signal
    if "::" in lhs:
        sig = lhs.split("::")[-1].strip()
        if sig:
            return ("env", sig, value, sig)

    # 最后兜底：原样写入 SetSignal
    return ("env", lhs, value, lhs if lhs else None)


def parse_set_step(label: str, body: str) -> DslSetStep:
    raw = body.strip()
    t, then_checks = _extract_then_checks(raw)
    t, keep_dyn = _extract_keep_dynamic_false(t)
    t, wait_seconds = _extract_wait_seconds(t)

    # 去掉多余空白
    t = " ".join(t.split())
    # 去掉开头的 "set"（整行可能是 "set A && B ..."，后续每段也可能有 set）
    if t.lower().startswith("set "):
        t = t[4:].strip()

    op_texts = _split_set_ops(t)
    ops: List[Tuple[str, str, Any]] = []
    for op_t in op_texts:
        kind, name, value, _ = _parse_set_op(op_t)
        ops.append((kind, name, value))

    return DslSetStep(
        label=label.upper(),
        raw=raw,
        keep_dynamic_false=keep_dyn,
        wait_seconds=wait_seconds,
        then_checks=then_checks,
        ops=tuple(ops),
    )


def _extract_timeout(text: str) -> Tuple[str, Optional[float]]:
    m = _RE_TIMEOUT.search(text)
    if not m:
        return text, None
    seconds = _time_to_seconds(m.group("t"), m.group("unit"))
    new_text = (text[: m.start()] + text[m.end() :]).strip()
    return new_text, seconds


def _extract_check_in_time(text: str) -> Tuple[str, Optional[float]]:
    m = _RE_CHECK_IN_TIME.search(text)
    if not m:
        return text, None
    seconds = _time_to_seconds(m.group("t"), m.group("unit"))
    new_text = (text[: m.start()] + text[m.end() :]).strip()
    return new_text, seconds


def _parse_check_predicate(text: str) -> Tuple[str, Dict[str, Any]]:
    # 输入是去掉 timeout/wait/checkInTime 后剩余的 "sig::... <predicate>"
    # 支持 "==3" 或 " == 3"；支持 "in {2,3}"；支持 "in 2..5"
    t = " ".join(text.split())
    # 先处理 in
    m_in = re.search(r"\bin\b", t, flags=re.IGNORECASE)
    if m_in:
        left = t[: m_in.start()].strip()
        right = t[m_in.end() :].strip()
        if right.startswith("{") and right.endswith("}"):
            inner = right[1:-1].strip()
            items = [p.strip() for p in inner.split(",") if p.strip()]
            values = [_parse_scalar(x) for x in items]
            return left, {"type": "in", "values": values}
        if ".." in right:
            a, b = right.split("..", 1)
            return left, {"type": "range", "min": _parse_scalar(a.strip()), "max": _parse_scalar(b.strip())}
        # 兜底：in 后面的原样
        return left, {"type": "in", "values": [_parse_scalar(right)]}

    # 处理 ==
    if "==" in t:
        left, right = t.split("==", 1)
        return left.strip(), {"type": "eq", "value": _parse_scalar(right.strip())}

    # 处理单 '='（容错）
    if "=" in t:
        left, right = t.split("=", 1)
        return left.strip(), {"type": "eq", "value": _parse_scalar(right.strip())}

    # 没有条件时默认等于 1
    return t.strip(), {"type": "eq", "value": 1}


def parse_check_step(label: str, body: str) -> DslCheckStep:
    raw = body.strip()
    t = raw
    t, wait_seconds = _extract_wait_seconds(t)
    t, timeout_seconds = _extract_timeout(t)
    t, duration_seconds = _extract_check_in_time(t)

    t = t.strip()
    if t.lower().startswith("check "):
        t = t[6:].strip()

    signal_expr, predicate = _parse_check_predicate(t)

    m_sig = _RE_SIG_CAN.match(signal_expr.strip())
    if m_sig:
        signal_name = m_sig.group("sig")
    else:
        # 兜底：取最后一个 :: 后的名称
        signal_name = signal_expr.split("::")[-1].strip()

    return DslCheckStep(
        label=label.upper(),
        raw=raw,
        signal_name=signal_name,
        predicate=predicate,
        timeout_seconds=timeout_seconds,
        duration_seconds=duration_seconds,
        wait_seconds=wait_seconds,
    )


def parse_dsl_case(text: str) -> DslCase:
    name: Optional[str] = None
    meta: Dict[str, str] = {}
    set_steps: List[DslSetStep] = []
    check_steps: List[DslCheckStep] = []

    # section 不是必须，但可以帮助人类组织；解析时依旧以 S/C 行为准
    _current_section: Optional[str] = None

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue

        m_case = _RE_CASE.match(line)
        if m_case:
            name = m_case.group("name").strip()
            continue

        m_meta = _RE_META.match(line)
        if m_meta:
            meta.update(_parse_meta_kv(m_meta.group("meta")))
            continue

        m_sec = _RE_SECTION.match(line)
        if m_sec:
            _current_section = m_sec.group("section").upper()
            continue

        m_s = _RE_S.match(line)
        if m_s:
            label = m_s.group("label").upper()
            body = m_s.group("body")
            set_steps.append(parse_set_step(label, body))
            continue

        m_c = _RE_C.match(line)
        if m_c:
            label = m_c.group("label").upper()
            body = m_c.group("body")
            check_steps.append(parse_check_step(label, body))
            continue

        # 未识别行直接忽略（避免因注释/格式差异中断批量转换）
        _ = _current_section

    if not name:
        raise ValueError("未找到 CASE: 行，无法确定 case 名称")

    return DslCase(
        name=name,
        meta=meta,
        set_steps=tuple(set_steps),
        check_steps=tuple(check_steps),
    )


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _to_py_action_set_sysvar(namespace: str, var_name: str, value: Any) -> Dict[str, Any]:
    return {"action": "SetSysVar", "namespace": namespace, "var_name": var_name, "value": value}


def _to_py_action_set_signal(signal: str, value: Any) -> Dict[str, Any]:
    return {"action": "SetSignal", "signal": signal, "value": value}


def _to_py_action_wait(seconds: float) -> Dict[str, Any]:
    return {"action": "Wait", "wait_time": seconds}


def _dsl_set_to_urltest(step: DslSetStep) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    if step.keep_dynamic_false:
        actions.append(_to_py_action_set_sysvar("simulink", "dynamic_disconnect", 1))

    for kind, name, value in step.ops:
        if kind == "sys":
            ns, var = name.split("::", 1)
            actions.append(_to_py_action_set_sysvar(ns, var, value))
        else:
            actions.append(_to_py_action_set_signal(name, value))

    if step.wait_seconds is not None:
        actions.append(_to_py_action_wait(step.wait_seconds))

    return {"description": step.label, "steps": actions}


def _dsl_check_to_urltest(step: DslCheckStep) -> Dict[str, Any]:
    pred = step.predicate
    if step.duration_seconds is not None:
        action: Dict[str, Any] = {
            "action": "CheckDuration",
            "signal": step.signal_name,
            "duration": step.duration_seconds,
        }
        if pred.get("type") == "eq":
            action["value"] = pred.get("value")
        else:
            # 保留非 eq 语义，避免信息丢失
            action["operator"] = pred.get("type")
            if pred.get("type") == "in":
                action["values"] = pred.get("values")
            elif pred.get("type") == "range":
                action["min"] = pred.get("min")
                action["max"] = pred.get("max")
        if step.wait_seconds is not None:
            action["wait_time"] = step.wait_seconds
        return {"description": step.label, "steps": [action]}

    action2: Dict[str, Any] = {"action": "CheckSignal", "signal": step.signal_name}
    if pred.get("type") == "eq":
        action2["value"] = pred.get("value")
    else:
        action2["operator"] = pred.get("type")
        if pred.get("type") == "in":
            action2["values"] = pred.get("values")
        elif pred.get("type") == "range":
            action2["min"] = pred.get("min")
            action2["max"] = pred.get("max")

    if step.timeout_seconds is not None:
        action2["timeout"] = step.timeout_seconds
    if step.wait_seconds is not None:
        action2["wait_time"] = step.wait_seconds
    return {"description": step.label, "steps": [action2]}


def dsl_case_to_py_struct(case: DslCase) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    urltests: List[Dict[str, Any]] = []

    # META: scenario_id -> SetScenario
    scenario_id = case.meta.get("scenario_id")
    if scenario_id is not None:
        try:
            sid_val: Any = int(scenario_id, 10)
        except Exception:
            sid_val = _parse_scalar(scenario_id)
        urltests.append({"description": "初始化场景", "steps": [{"action": "SetScenario", "scenario_id": sid_val}]})

    checks_by_label: Dict[str, DslCheckStep] = {c.label.upper(): c for c in case.check_steps}
    used_checks: set[str] = set()

    # 先按 set 顺序输出，遇到 then CHECK 就立刻插入对应检查
    for s in case.set_steps:
        urltests.append(_dsl_set_to_urltest(s))
        for cref in s.then_checks:
            c = checks_by_label.get(cref.upper())
            if c is None:
                continue
            urltests.append(_dsl_check_to_urltest(c))
            used_checks.add(c.label.upper())

    # 再把剩余的 check（未被 then CHECK 使用的）按原出现顺序追加
    for c in case.check_steps:
        if c.label.upper() in used_checks:
            continue
        urltests.append(_dsl_check_to_urltest(c))

    # URLmapping：收集所有 env/sig 信号（SetSignal + Check*）
    mapping_candidates: List[str] = []
    for t in urltests:
        for act in t.get("steps", []):
            a = act.get("action")
            if a == "SetSignal":
                mapping_candidates.append(str(act.get("signal")))
            elif a in ("CheckSignal", "CheckDuration"):
                mapping_candidates.append(str(act.get("signal")))
    urlmapping = _unique_preserve_order([x for x in mapping_candidates if x and x != "None"])

    return case.name, urlmapping, urltests


def render_py_case(name: str, urlmapping: Sequence[str], urltests: Sequence[Dict[str, Any]]) -> str:
    # 生成可直接 import 的 python 文件
    # 使用 pprint 以获得稳定、可读的字面量输出
    mapping_str = pformat(list(urlmapping), width=120, sort_dicts=False)
    tests_str = pformat(list(urltests), width=120, sort_dicts=False)
    return (
        "# -*- coding: utf-8 -*-\n"
        f'__name__ = {name!r}\n'
        f"URLmapping = {mapping_str}\n\n"
        f"URLTests = {tests_str}\n"
    )


def convert_file(in_path: Path, out_path: Path, encoding: str = "utf-8") -> None:
    text = in_path.read_text(encoding=encoding, errors="replace")
    dsl = parse_dsl_case(text)
    name, mapping, tests = dsl_case_to_py_struct(dsl)
    out_text = render_py_case(name, mapping, tests)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")


def _iter_dsl_files(input_path: Path, glob_pattern: str) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    # 目录递归
    return sorted(input_path.rglob(glob_pattern))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="批量将 .dsl case 转换为目标 .py case 格式")
    ap.add_argument("-i", "--input", required=True, help="输入 .dsl 文件或目录")
    ap.add_argument("-o", "--output-dir", default="", help="输出目录（默认与输入文件同目录）")
    ap.add_argument("--glob", default="*.dsl", help="当 input 为目录时的匹配模式（默认 *.dsl）")
    ap.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8，错误替换）")
    args = ap.parse_args(argv)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        raise SystemExit(f"输入路径不存在: {in_path}")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    dsl_files = _iter_dsl_files(in_path, args.glob)
    if not dsl_files:
        raise SystemExit(f"未找到任何匹配文件：input={in_path} glob={args.glob}")

    # 当 input 为目录且指定了 output-dir 时，保留相对目录结构，避免文件名冲突覆盖
    base_dir = in_path if in_path.is_dir() else None

    ok = 0
    failed: List[Tuple[Path, str]] = []
    for f in dsl_files:
        try:
            if out_dir is None:
                out_path = f.with_suffix(".py")
            else:
                if base_dir is not None:
                    rel = f.relative_to(base_dir)
                else:
                    rel = Path(f.name)
                out_path = (out_dir / rel).with_suffix(".py")
            convert_file(f, out_path, encoding=args.encoding)
            ok += 1
        except Exception as e:
            failed.append((f, str(e)))

    if failed:
        msg = "\n".join([f"- {p}: {err}" for p, err in failed])
        print(f"转换完成：成功 {ok}，失败 {len(failed)}\n失败列表：\n{msg}")
        return 2

    print(f"转换完成：成功 {ok}，失败 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

