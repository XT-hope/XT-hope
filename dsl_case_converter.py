#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将第一种 DSL 文本 case（.dsl）批量转换为第二种 Python case（.py）。

支持要点（按需求描述实现）：
- 解析 CASE / META 头部
- 解析 S1/S2/... (set) 与 C1/C2/... (check)
- 支持 set 的可选参数：wait、keep_dynamic false、then CHECK C1,C2,...
- 支持 check 的可选参数：timeoutOfCheck、checkInTime、wait
- 时间单位自动从 ms/s 转为秒（float）
- URLmapping：收集所有 env::CAN... 或 sig::CAN... 中的 signal_name（最后一段）
- keep_dynamic false：在该 set 动作之前插入 simulink.dynamic_disconnect=1
- then CHECK：在该 set 之后立刻插入对应 Cn 的检查步骤；未被 then CHECK 引用的 Cn 仍会在最后追加

用法示例：
  python3 dsl_case_converter.py --input /path/to/cases --output /path/to/out
  python3 dsl_case_converter.py --input /path/to/case.dsl --output /path/to/out_dir
"""

from __future__ import annotations

import argparse
import os
import pprint
import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class DslParseError(ValueError):
    pass


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


_TIME_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s)\s*$", re.IGNORECASE)


def parse_time_to_seconds(time_str: str) -> float:
    """
    支持：1500ms / 1.5s / 5s / 200 ms
    统一返回秒（float）。
    """
    m = _TIME_RE.match(time_str)
    if not m:
        raise DslParseError(f"无法解析时间: {time_str!r}")
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "ms":
        return value / 1000.0
    if unit == "s":
        return value
    raise DslParseError(f"不支持的时间单位: {unit!r}")


def parse_value(value_str: str) -> Any:
    """
    将 DSL 中的 value 尽量转换为 Python 数值：
    - 0x.. -> int
    - 整数/浮点 -> int/float
    - 其他 -> 原字符串
    """
    s = value_str.strip()
    if not s:
        return s
    if s.lower().startswith("0x"):
        try:
            return int(s, 16)
        except ValueError:
            return s
    # int
    if re.fullmatch(r"[+-]?\d+", s):
        try:
            return int(s)
        except ValueError:
            return s
    # float
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def parse_meta(meta_text: str) -> Dict[str, str]:
    """
    META: 后面的键值对用空格分隔，键和值用等号分隔。
    若 value 有空格，建议写成双引号；这里用 shlex 支持引号。
    """
    meta_text = meta_text.strip()
    if not meta_text:
        return {}
    out: Dict[str, str] = {}
    for tok in shlex.split(meta_text):
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


@dataclass(frozen=True)
class SignalRef:
    kind: str  # "env" | "sig" | "sys"
    can_channel: Optional[int] = None
    message_name: Optional[str] = None
    namespace: Optional[str] = None
    name: str = ""  # signal_name or sys var_name


def parse_signal_ref(text: str) -> Tuple[SignalRef, Optional[str]]:
    """
    解析信号引用（含可选 =value）：
    - env::CAN 1::MSG::SIG=0x1
    - sig::CAN 1::MSG::SIG
    - sys::Namespace::Var=0x1
    返回 (SignalRef, value_str_or_None)
    """
    s = text.strip()

    # env/sig CAN
    m = re.match(r"^(env|sig)::CAN\s+(\d+)::([^:]+)::(.+)$", s)
    if m:
        kind = m.group(1)
        ch = int(m.group(2))
        msg = m.group(3).strip()
        rest = m.group(4).strip()
        if "=" in rest:
            sig_name, value_str = rest.split("=", 1)
            sig_name = sig_name.strip()
            value_str = value_str.strip()
        else:
            sig_name, value_str = rest.strip(), None
        return (
            SignalRef(kind=kind, can_channel=ch, message_name=msg, name=sig_name),
            value_str,
        )

    # sys
    m = re.match(r"^sys::([^:]+)::(.+)$", s)
    if m:
        ns = m.group(1).strip()
        rest = m.group(2).strip()
        if "=" in rest:
            var_name, value_str = rest.split("=", 1)
            var_name = var_name.strip()
            value_str = value_str.strip()
        else:
            var_name, value_str = rest.strip(), None
        return (SignalRef(kind="sys", namespace=ns, name=var_name), value_str)

    raise DslParseError(f"无法解析信号引用: {text!r}")


@dataclass
class SetStep:
    sid: str  # "S1"
    raw: str
    assignments: List[Tuple[SignalRef, Any]]  # 按出现顺序执行
    wait_s: Optional[float]
    keep_dynamic_false: bool
    then_checks: List[str]  # ["C1", "C2", ...]


@dataclass
class CheckCondition:
    op: str  # "eq" | "in_set" | "range"
    value: Any


@dataclass
class CheckStep:
    cid: str  # "C1"
    raw: str
    target: SignalRef
    condition: CheckCondition
    timeout_s: Optional[float]
    check_in_time_s: Optional[float]
    wait_s: Optional[float]


@dataclass
class CaseDsl:
    name: str
    meta: Dict[str, str]
    sets: List[SetStep]
    checks: List[CheckStep]


def _extract_option(pattern: re.Pattern[str], text: str) -> Tuple[Optional[str], str]:
    m = pattern.search(text)
    if not m:
        return None, text
    value = m.group(1)
    new_text = (text[: m.start()] + " " + text[m.end() :]).strip()
    return value, new_text


_SET_WAIT_OPT_RE = re.compile(r"\bwait\s+([0-9]+(?:\.[0-9]+)?\s*(?:ms|s))\b", re.IGNORECASE)
# 同时兼容：keep_dynamic false / keepDynamic false / keepdynamic false
_SET_KEEP_DYNAMIC_RE = re.compile(r"\bkeep(?:_)?dynamic\s+(true|false)\b", re.IGNORECASE)
_SET_THEN_CHECK_RE = re.compile(r"\bthen\s+CHECK\s+(.+)$", re.IGNORECASE)

_CHECK_TIMEOUT_RE = re.compile(
    r"\btimeoutOfCheck\s+([0-9]+(?:\.[0-9]+)?\s*(?:ms|s))\b", re.IGNORECASE
)
_CHECK_CHECKINTIME_RE = re.compile(
    r"\bcheckInTime\s+([0-9]+(?:\.[0-9]+)?\s*(?:ms|s))\b", re.IGNORECASE
)
_CHECK_WAIT_RE = re.compile(r"\bwait\s+([0-9]+(?:\.[0-9]+)?\s*(?:ms|s))\b", re.IGNORECASE)


def parse_set_step(sid: str, content: str) -> SetStep:
    raw = content.strip()
    if not raw.lower().startswith("set "):
        raise DslParseError(f"{sid}: 不是 set 步骤: {raw!r}")
    rest = raw[4:].strip()

    # then CHECK ...
    then_checks: List[str] = []
    m_then = _SET_THEN_CHECK_RE.search(rest)
    if m_then:
        then_part = m_then.group(1).strip()
        rest = rest[: m_then.start()].strip()
        for part in re.split(r"[,\s]+", then_part):
            part = part.strip()
            if not part:
                continue
            if not re.fullmatch(r"C\d+", part, re.IGNORECASE):
                raise DslParseError(f"{sid}: then CHECK 中包含非法 Cn: {part!r}")
            then_checks.append(part.upper())

    # keep_dynamic
    keep_dynamic_false = False
    m_kd = _SET_KEEP_DYNAMIC_RE.search(rest)
    if m_kd:
        kd_val = m_kd.group(1).lower()
        keep_dynamic_false = kd_val == "false"
        rest = (rest[: m_kd.start()] + " " + rest[m_kd.end() :]).strip()

    # wait
    wait_token, rest = _extract_option(_SET_WAIT_OPT_RE, rest)
    wait_s = parse_time_to_seconds(wait_token) if wait_token else None

    # 支持：set A=1 && B=2 && sys::X::Y=0x1
    # 注意：&& 两侧可能有空格
    parts = [p.strip() for p in re.split(r"\s*&&\s*", rest) if p.strip()]
    if not parts:
        raise DslParseError(f"{sid}: set 内容为空: {raw!r}")

    assignments: List[Tuple[SignalRef, Any]] = []
    for part in parts:
        target, value_str = parse_signal_ref(part)
        value = parse_value(value_str) if value_str is not None else 1
        assignments.append((target, value))

    return SetStep(
        sid=sid.upper(),
        raw=raw,
        assignments=assignments,
        wait_s=wait_s,
        keep_dynamic_false=keep_dynamic_false,
        then_checks=then_checks,
    )


def _parse_check_condition(cond_text: str) -> Tuple[str, str]:
    """
    将条件部分切分为：signal_spec_str, expr_str
    支持：
    - sig::... == 3
    - sig::...==3
    - sig::... in {2,3}
    - sig::... in 2..5
    """
    s = cond_text.strip()
    # 优先解析 " in "
    m_in = re.search(r"\s+\bin\b\s+", s, flags=re.IGNORECASE)
    if m_in:
        left = s[: m_in.start()].strip()
        right = s[m_in.end() :].strip()
        return left, f"in {right}"
    # == or =
    m_eq = re.search(r"\s*==\s*|\s*=\s*", s)
    if m_eq:
        left = s[: m_eq.start()].strip()
        right = s[m_eq.end() :].strip()
        return left, f"== {right}"
    raise DslParseError(f"无法解析 check 条件: {cond_text!r}")


def parse_check_step(cid: str, content: str) -> CheckStep:
    raw = content.strip()
    if not raw.lower().startswith("check "):
        raise DslParseError(f"{cid}: 不是 check 步骤: {raw!r}")
    rest = raw[6:].strip()

    timeout_token, rest = _extract_option(_CHECK_TIMEOUT_RE, rest)
    check_in_time_token, rest = _extract_option(_CHECK_CHECKINTIME_RE, rest)
    wait_token, rest = _extract_option(_CHECK_WAIT_RE, rest)

    timeout_s = parse_time_to_seconds(timeout_token) if timeout_token else None
    check_in_time_s = parse_time_to_seconds(check_in_time_token) if check_in_time_token else None
    wait_s = parse_time_to_seconds(wait_token) if wait_token else None

    sig_part, expr_part = _parse_check_condition(rest)
    target, _ = parse_signal_ref(sig_part)
    if target.kind != "sig":
        raise DslParseError(f"{cid}: check 目标必须是 sig::CAN...，实际为: {sig_part!r}")

    expr_part = expr_part.strip()
    if expr_part.lower().startswith("=="):
        v = expr_part[2:].strip()
        cond = CheckCondition(op="eq", value=parse_value(v))
    elif expr_part.lower().startswith("in"):
        rhs = expr_part[2:].strip()
        # {2,3}
        m_set = re.fullmatch(r"\{(.+)\}", rhs)
        if m_set:
            items = [x.strip() for x in m_set.group(1).split(",") if x.strip()]
            cond = CheckCondition(op="in_set", value=[parse_value(x) for x in items])
        else:
            # 2..5
            m_rng = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*\.\.\s*([+-]?\d+(?:\.\d+)?)", rhs)
            if not m_rng:
                raise DslParseError(f"{cid}: 无法解析 in 条件: {rhs!r}")
            a = parse_value(m_rng.group(1))
            b = parse_value(m_rng.group(2))
            cond = CheckCondition(op="range", value={"min": a, "max": b})
    else:
        raise DslParseError(f"{cid}: 不支持的条件表达式: {expr_part!r}")

    return CheckStep(
        cid=cid.upper(),
        raw=raw,
        target=target,
        condition=cond,
        timeout_s=timeout_s,
        check_in_time_s=check_in_time_s,
        wait_s=wait_s,
    )


def parse_dsl_text(text: str) -> CaseDsl:
    text = _strip_bom(text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]

    case_name: Optional[str] = None
    meta: Dict[str, str] = {}
    raw_sets: List[Tuple[int, str, str]] = []  # (num, sid, content)
    raw_checks: List[Tuple[int, str, str]] = []

    for ln in lines:
        if ln.upper().startswith("CASE:"):
            case_name = ln.split(":", 1)[1].strip()
            continue
        if ln.upper().startswith("META:"):
            meta = parse_meta(ln.split(":", 1)[1])
            continue
        if re.fullmatch(r"\[SET\]|\[CHECK\]", ln.strip(), flags=re.IGNORECASE):
            continue

        m_s = re.match(r"^(S(\d+))\s*:\s*(.+)$", ln, flags=re.IGNORECASE)
        if m_s:
            sid = m_s.group(1).upper()
            num = int(m_s.group(2))
            content = m_s.group(3).strip()
            raw_sets.append((num, sid, content))
            continue

        m_c = re.match(r"^(C(\d+))\s*:\s*(.+)$", ln, flags=re.IGNORECASE)
        if m_c:
            cid = m_c.group(1).upper()
            num = int(m_c.group(2))
            content = m_c.group(3).strip()
            raw_checks.append((num, cid, content))
            continue

    if not case_name:
        raise DslParseError("缺少 CASE: ... 头部")

    raw_sets.sort(key=lambda x: x[0])
    raw_checks.sort(key=lambda x: x[0])

    sets = [parse_set_step(sid, content) for _, sid, content in raw_sets]
    checks = [parse_check_step(cid, content) for _, cid, content in raw_checks]

    return CaseDsl(name=case_name, meta=meta, sets=sets, checks=checks)


def _append_mapping(mapping: List[str], seen: set, signal_name: str) -> None:
    if signal_name not in seen:
        seen.add(signal_name)
        mapping.append(signal_name)


def convert_case_to_python(case: CaseDsl) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    返回 (URLmapping, URLTests)
    """
    checks_by_id: Dict[str, CheckStep] = {c.cid: c for c in case.checks}

    url_mapping: List[str] = []
    seen: set = set()

    url_tests: List[Dict[str, Any]] = []

    # scenario_id -> 首步初始化
    scenario_id = case.meta.get("scenario_id")
    if scenario_id is not None:
        try:
            scenario_id_val = int(scenario_id)
        except ValueError:
            scenario_id_val = None
        if scenario_id_val is not None:
            url_tests.append(
                {"description": "初始化场景", "steps": [{"action": "SetScenario", "scenario_id": scenario_id_val}]}
            )

    referenced_checks: set = set()

    def emit_check(cid: str) -> None:
        cid = cid.upper()
        c = checks_by_id.get(cid)
        if not c:
            raise DslParseError(f"then CHECK 引用了不存在的步骤: {cid}")

        _append_mapping(url_mapping, seen, c.target.name)

        # checkInTime -> CheckDuration
        if c.check_in_time_s is not None:
            action = "CheckDuration"
            step: Dict[str, Any] = {"action": action, "signal": c.target.name, "duration": c.check_in_time_s}
        else:
            action = "CheckSignal"
            step = {"action": action, "signal": c.target.name}
            if c.timeout_s is not None:
                step["timeout"] = c.timeout_s

        # 条件
        if c.condition.op == "eq":
            step["value"] = c.condition.value
        elif c.condition.op == "in_set":
            step["value"] = c.condition.value
            step["operator"] = "in"
        elif c.condition.op == "range":
            step["value"] = c.condition.value
            step["operator"] = "range"
        else:
            raise DslParseError(f"{cid}: 不支持的 condition op: {c.condition.op!r}")

        if c.wait_s is not None:
            # 按你给的示例：check 后的 wait 写在同一个 dict 里
            step["wait_time"] = c.wait_s

        url_tests.append({"description": cid, "steps": [step]})

    for s in case.sets:
        steps: List[Dict[str, Any]] = []

        # keep_dynamic false -> 先断动力学
        if s.keep_dynamic_false:
            steps.append(
                {"action": "SetSysVar", "namespace": "simulink", "var_name": "dynamic_disconnect", "value": 1}
            )

        for target, value in s.assignments:
            if target.kind == "env":
                _append_mapping(url_mapping, seen, target.name)
                steps.append({"action": "SetSignal", "signal": target.name, "value": value})
            elif target.kind == "sys":
                steps.append(
                    {
                        "action": "SetSysVar",
                        "namespace": target.namespace or "",
                        "var_name": target.name,
                        "value": value,
                    }
                )
            else:
                raise DslParseError(f"{s.sid}: set 目标不支持的 kind: {target.kind!r}")

        if s.wait_s is not None:
            steps.append({"action": "Wait", "wait_time": s.wait_s})

        url_tests.append({"description": s.sid, "steps": steps})

        # then CHECK: 立即插入对应的 Cn
        for cid in s.then_checks:
            referenced_checks.add(cid.upper())
            emit_check(cid)

    # 追加未被 then CHECK 引用的检查
    for c in case.checks:
        if c.cid not in referenced_checks:
            emit_check(c.cid)

    return url_mapping, url_tests


def render_python_case(case: CaseDsl) -> str:
    url_mapping, url_tests = convert_case_to_python(case)

    lines: List[str] = []
    lines.append("# -*- coding: utf-8 -*-")
    lines.append(f'__name__ = {pprint.pformat(case.name)}')

    # META 以注释保留（不影响 runner）
    if case.meta:
        lines.append("")
        lines.append("# META（原 DSL）")
        for k, v in case.meta.items():
            lines.append(f"# {k}={v}")

    lines.append("")
    lines.append(f"URLmapping = {pprint.pformat(url_mapping, width=120)}")
    lines.append("")
    lines.append(f"URLTests = {pprint.pformat(url_tests, width=120)}")
    lines.append("")
    return "\n".join(lines)


def iter_input_dsl_files(input_path: str) -> List[str]:
    if os.path.isdir(input_path):
        out: List[str] = []
        for root, _, files in os.walk(input_path):
            for fn in files:
                if fn.lower().endswith(".dsl"):
                    out.append(os.path.join(root, fn))
        out.sort()
        return out
    return [input_path]


def convert_files(input_path: str, output_dir: str, overwrite: bool) -> List[Tuple[str, str]]:
    os.makedirs(output_dir, exist_ok=True)
    converted: List[Tuple[str, str]] = []
    for src in iter_input_dsl_files(input_path):
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
        case = parse_dsl_text(text)
        py_text = render_python_case(case)

        # 输出文件名：优先使用 CASE 名称；否则用源文件名
        out_name = f"{case.name}.py".replace("/", "_")
        dst = os.path.join(output_dir, out_name)
        if (not overwrite) and os.path.exists(dst):
            raise FileExistsError(f"输出文件已存在（未开启 --overwrite）: {dst}")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(py_text)
        converted.append((src, dst))
    return converted


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="批量将 .dsl case 转换为 .py case（URLTests/URLmapping 格式）")
    p.add_argument("--input", required=True, help="输入 .dsl 文件或包含 .dsl 的目录")
    p.add_argument("--output", required=True, help="输出目录（生成 .py 文件）")
    p.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件")
    args = p.parse_args(argv)

    converted = convert_files(args.input, args.output, overwrite=args.overwrite)
    print(f"转换完成：{len(converted)} 个文件")
    for src, dst in converted:
        print(f"- {src} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

