#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""批量把 DSL case（.dsl 文本）转换成 URLTests 形式（.py 脚本）。

目标格式（输出 .py）：
- __name__: case 名称
- URLmapping: 收集所有 env::CAN / sig::CAN 中出现的 signal_name
- URLTests: 步骤列表

支持：
- CASE/META 头部解析（META 支持 value 含空格）
- Sx set: sys::namespace::var / env::CAN n::msg::signal
- set 中多操作：使用 && 连接
- keep_dynamic false / keepDynamic false：在该步骤最前插入 dynamic_disconnect
- wait 500ms / 5s：Wait(秒)
- then CHECK C1,C2：把指定 Cx 的检查插入到该 set 之后，并从最终 [CHECK] 列表中剔除
- check: == / in {a,b} / in a..b
- timeoutOfCheck / checkInTime / wait 参数（单位 ms/s）

用法：
- 转单文件：python3 dsl_case_converter.py /path/to/case.dsl
- 转目录（递归）：python3 dsl_case_converter.py /path/to/dsl_dir --output-dir /path/to/out
- 默认输出到输入文件同目录，扩展名改为 .py
"""

from __future__ import annotations

import argparse
import os
import pprint
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union


Number = Union[int, float]
Value = Union[Number, str, List[Number], Dict[str, Number]]


_TIME_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>ms|s)\s*$", re.IGNORECASE)

commen_signals_for_ulrmapping=[
    "Speed_Signal_151_S",
    "Rnk_hw",
    "DNP_warning_text_info",
    "CSW_Enable_S"
]

def parse_time_seconds(text: str) -> float:
    """解析 200ms / 5s 为秒(float)。"""
    m = _TIME_RE.match(text)
    if not m:
        raise ValueError(f"无法解析时间: {text!r}")
    num = float(m.group("num"))
    unit = m.group("unit").lower()
    if unit == "ms":
        return num / 1000.0
    return num


def parse_value(text: str) -> Value:
    """把右值解析成 int/float/str。

    - 0x.. 视为十六进制 int
    - 纯数字视为 int
    - 含小数点视为 float
    - 否则原样 str（去除首尾空白）
    """
    s = text.strip()
    if s == "":
        return ""
    # 去掉可能的尾随分号/逗号
    s = s.rstrip(";,")

    # bool 风格
    if s.lower() in {"true", "false"}:
        return 1 if s.lower() == "true" else 0

    # 尝试 int(base=0) 支持 0x.. / 0o.. / 0b..
    try:
        if re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", s) or re.fullmatch(r"[+-]?\d+", s):
            return int(s, 0)
    except ValueError:
        pass

    # float
    try:
        if re.fullmatch(r"[+-]?\d*\.\d+", s) or re.fullmatch(r"[+-]?\d+\.\d*", s):
            return float(s)
    except ValueError:
        pass

    return s


def parse_meta_kv(meta_text: str) -> Dict[str, str]:
    """解析 META 行：key=value key2=value2 ...

    允许 value 内含空格：使用 key= 的位置切片。
    """
    s = meta_text.strip()
    if not s:
        return {}

    matches = list(re.finditer(r"(?P<key>[A-Za-z0-9_]+)=", s))
    if not matches:
        return {}

    out: Dict[str, str] = {}
    for i, m in enumerate(matches):
        key = m.group("key")
        val_start = m.end()
        val_end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        val = s[val_start:val_end].strip()
        out[key] = val
    return out


@dataclass(frozen=True)
class Assignment:
    kind: str  # "sys" | "env"
    namespace: Optional[str]
    name: str  # sys var_name 或 env/sig signal_name
    value: Value


@dataclass(frozen=True)
class DslSetStep:
    sid: str
    assignments: List[Assignment]
    dynamic_disconnect: bool
    wait_s: Optional[float]
    then_checks: List[str]
    comment: Optional[str] = None


@dataclass(frozen=True)
class CheckCondition:
    mode: str  # "eq" | "in_set" | "in_range"
    value: Value


@dataclass(frozen=True)
class DslCheckDef:
    cid: str
    signal: str
    condition: CheckCondition
    timeout_s: Optional[float]
    duration_s: Optional[float]
    wait_s: Optional[float]
    comment: Optional[str] = None


@dataclass
class DslCase:
    name: str
    meta: Dict[str, str]
    sets: List[DslSetStep]
    checks_in_order: List[str]
    checks: Dict[str, DslCheckDef]


def _strip_blank_and_comments(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # 忽略纯章节标签
        if re.fullmatch(r"\[[A-Za-z_]+\]", line):
            continue
        out.append(line)
    return out


def _find_first_keyword_pos(text: str, keywords: Sequence[str]) -> Optional[int]:
    low = text.lower()
    positions = [low.find(k.lower()) for k in keywords]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else None


def _parse_signal_ref(kind: str, left: str) -> Tuple[Optional[str], str]:
    """解析 sys/env/sig 左侧引用，返回 (namespace, name)。"""
    s = " ".join(left.strip().split())
    print(s)

    if kind == "sys":
        # 支持name中包含点号、下划线、字母、数字
        m = re.match(r"^sys::(?P<ns>[^:]+)::(?P<name>[A-Za-z0-9_.]+)$", s)
        if not m:
            raise ValueError(f"无法解析 sys 引用: {left!r}")
        return m.group("ns"), m.group("name")

    # env 或 sig：只取最后的 signal_name
    m = re.match(
        r"^(?:env|sig)::CAN\s+(?P<ch>\d+)::(?P<msg>[^:]+)::(?P<sig>[A-Za-z0-9_]+)$",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        # 兜底：直接取最后一段 ::xxx
        if "::" in s:
            return None, s.split("::")[-1]
        raise ValueError(f"无法解析 {kind} 引用: {left!r}")
    return None, m.group("sig")


def parse_set_step(line: str) -> DslSetStep:
    m = re.match(r"^(?P<sid>S\d+)\s*:\s*(?P<body>.+)$", line, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"不是合法 Set 行: {line!r}")
    sid = m.group("sid")
    body = m.group("body").strip()

    if not body.lower().startswith("set "):
        raise ValueError(f"Set 行缺少 set 关键字: {line!r}")

    # comment
    comment: Optional[str] = None
    comment_m = re.search(r"\bcomment\s+(?P<val>.+?)\s*$", body, flags=re.IGNORECASE)
    if comment_m:
        comment = comment_m.group("val").strip().strip('"\'')

    # then CHECK
    then_checks: List[str] = []
    then_m = re.search(r"\bthen\s+CHECK\s+(?P<ids>.+)$", body, flags=re.IGNORECASE)
    if then_m:
        ids_part = then_m.group("ids").strip()
        ids = [x.strip() for x in re.split(r"[\s,]+", ids_part) if x.strip()]
        then_checks = [x for x in ids if re.fullmatch(r"C\d+", x, flags=re.IGNORECASE)]

    # keepDynamic / keep_dynamic
    dynamic_disconnect = False
    keep_m = re.search(r"\bkeep(?:_dynamic|Dynamic)\s+(?P<val>true|false|0|1)\b", body, flags=re.IGNORECASE)
    if keep_m:
        v = keep_m.group("val").lower()
        # 需求：keepDynamic false 表示切断动力学 -> dynamic_disconnect=1
        dynamic_disconnect = v in {"false", "0"}

    # wait
    wait_s: Optional[float] = None
    wait_m = re.search(r"\bwait\s+(?P<t>\S+)\b", body, flags=re.IGNORECASE)
    if wait_m:
        wait_s = parse_time_seconds(wait_m.group("t"))

    # 截取 assignments 区（去掉参数部分）
    cut_pos = _find_first_keyword_pos(body, [" then check ", " keep_dynamic ", " keepdynamic ", " wait ", " comment "])
    expr = body
    if cut_pos is not None:
        expr = body[:cut_pos].strip()

    expr = expr.strip()
    if expr.lower().startswith("set "):
        expr = expr[4:].strip()

    parts = [p.strip() for p in re.split(r"\s*&&\s*", expr) if p.strip()]
    assignments: List[Assignment] = []

    for part in parts:
        p = part
        if p.lower().startswith("set "):
            p = p[4:].strip()

        if "=" in p:
            left, right = p.split("=", 1)
            left = left.strip()
            right = right.strip()
        else:
            # 示例里出现过 set sys::...（无赋值），按 1 处理
            left, right = p.strip(), "1"

        left_norm = " ".join(left.split())

        if left_norm.lower().startswith("sys::"):
            ns, name = _parse_signal_ref("sys", left_norm)
            assignments.append(Assignment(kind="sys", namespace=ns, name=name, value=parse_value(right)))
        else:
            # env::CAN ...
            _, sig_name = _parse_signal_ref("env", left_norm)
            assignments.append(Assignment(kind="env", namespace=None, name=sig_name, value=parse_value(right)))

    return DslSetStep(
        sid=sid,
        assignments=assignments,
        dynamic_disconnect=dynamic_disconnect,
        wait_s=wait_s,
        then_checks=[c.upper() for c in then_checks],
        comment=comment,
    )


def parse_check_def(line: str) -> DslCheckDef:
    m = re.match(r"^(?P<cid>C\d+)\s*:\s*(?P<body>.+)$", line, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"不是合法 Check 行: {line!r}")
    cid = m.group("cid").upper()
    body = m.group("body").strip()

    if not body.lower().startswith("check "):
        raise ValueError(f"Check 行缺少 check 关键字: {line!r}")

    # comment
    comment: Optional[str] = None
    comment_m = re.search(r"\bcomment\s+(?P<val>.+?)\s*$", body, flags=re.IGNORECASE)
    if comment_m:
        comment = comment_m.group("val").strip().strip('"\'')

    timeout_s: Optional[float] = None
    duration_s: Optional[float] = None
    wait_s: Optional[float] = None

    t_m = re.search(r"\btimeout\s+(?P<t>\S+)\b", body, flags=re.IGNORECASE)
    if t_m:
        timeout_s = parse_time_seconds(t_m.group("t"))

    d_m = re.search(r"\bduration\s+(?P<t>\S+)\b", body, flags=re.IGNORECASE)
    if d_m:
        duration_s = parse_time_seconds(d_m.group("t"))

    w_m = re.search(r"\bwait\s+(?P<t>\S+)\b", body, flags=re.IGNORECASE)
    if w_m:
        wait_s = parse_time_seconds(w_m.group("t"))

    cut_pos = _find_first_keyword_pos(body, [" timeout ", " duration ", " wait ", " comment "])
    expr = body
    if cut_pos is not None:
        expr = body[:cut_pos].strip()

    expr = expr.strip()
    expr = expr[6:].strip()  # remove leading "check "

    # 支持两种格式：
    # 格式1: sig::CAN ...::Signal ==3 | in {2,3} | in 2..5
    # 格式2: sys::namespace::name == value
    sig_m = re.match(
        r"^(?P<ref>sig::CAN\s+\d+::[^:]+::[A-Za-z0-9_]+)\s*(?P<rest>.*)$",
        expr,
        flags=re.IGNORECASE,
    )
    sys_m = None
    if not sig_m:
        # 尝试匹配 sys:: 格式
        sys_m = re.match(
            r"^(?P<ref>sys::[^:]+::[A-Za-z0-9_.]+)\s*(?P<rest>.*)$",
            expr,
            flags=re.IGNORECASE,
        )

    if not sig_m and not sys_m:
        raise ValueError(f"无法解析 Check 表达式: {line!r}")

    if sig_m:
        sig_ref = sig_m.group("ref").strip()
        rest = sig_m.group("rest").strip()
        _, signal = _parse_signal_ref("sig", sig_ref)
    else:
        sig_ref = sys_m.group("ref").strip()
        rest = sys_m.group("rest").strip()
        _, signal = _parse_signal_ref("sys", sig_ref)

    # 条件
    if re.search(r"\bin\s*\{", rest, flags=re.IGNORECASE):
        in_m = re.search(r"\bin\s*\{(?P<vals>[^}]+)\}\s*$", rest, flags=re.IGNORECASE)
        if not in_m:
            raise ValueError(f"无法解析 in {{}} 条件: {line!r}")
        vals_raw = [x.strip() for x in in_m.group("vals").split(",") if x.strip()]
        vals_num: List[Number] = []
        for v in vals_raw:
            pv = parse_value(v)
            if isinstance(pv, (int, float)):
                vals_num.append(pv)
            else:
                raise ValueError(f"in {{}} 中发现非数字: {v!r}")
        cond = CheckCondition(mode="in_set", value=vals_num)
    else:
        range_m = re.search(r"\bin\s+(?P<a>[+-]?\d+)\.\.(?P<b>[+-]?\d+)\s*$", rest, flags=re.IGNORECASE)
        if range_m:
            a = int(range_m.group("a"), 0)
            b = int(range_m.group("b"), 0)
            cond = CheckCondition(mode="in_range", value={"min": a, "max": b})
        else:
            eq_m = re.search(r"==\s*(?P<v>\S+)\s*$", rest)
            if not eq_m:
                eq_m = re.search(r"=\s*(?P<v>\S+)\s*$", rest)
            if not eq_m:
                raise ValueError(f"无法解析 == 条件: {line!r}")
            v = parse_value(eq_m.group("v"))
            cond = CheckCondition(mode="eq", value=v)

    return DslCheckDef(
        cid=cid,
        signal=signal,
        condition=cond,
        timeout_s=timeout_s,
        duration_s=duration_s,
        wait_s=wait_s,
        comment=comment,
    )


def parse_dsl_case(text: str, fallback_name: str) -> DslCase:
    lines = _strip_blank_and_comments(text.splitlines())

    case_name = fallback_name
    meta: Dict[str, str] = {}
    set_steps: List[DslSetStep] = []
    checks: Dict[str, DslCheckDef] = {}
    checks_in_order: List[str] = []

    for line in lines:
        if line.upper().startswith("CASE:"):
            case_name = line.split(":", 1)[1].strip() or fallback_name
            continue
        if line.upper().startswith("META:"):
            meta_text = line.split(":", 1)[1].strip()
            meta = parse_meta_kv(meta_text)
            continue

        if re.match(r"^S\d+\s*:", line, flags=re.IGNORECASE):
            set_steps.append(parse_set_step(line))
            continue
        if re.match(r"^C\d+\s*:", line, flags=re.IGNORECASE):
            c = parse_check_def(line)
            checks[c.cid] = c
            checks_in_order.append(c.cid)
            continue

        # 未识别行：忽略（避免因注释/扩展语法导致全失败）

    return DslCase(
        name=case_name,
        meta=meta,
        sets=set_steps,
        checks_in_order=checks_in_order,
        checks=checks,
    )


def _check_to_actions(c: DslCheckDef):
    base: Dict[str, Any]
    if c.duration_s is not None:
        base = {
            "action": "CheckDuration",
            "signal": c.signal,
            "value": c.condition.value,
            "duration": float(c.duration_s),
        }
    else:
        base = {
            "action": "CheckSignal",
            "signal": c.signal,
            "value": c.condition.value,
        }
        if c.timeout_s is not None:
            base["timeout"] = float(c.timeout_s)

    action_wait = None
    if c.wait_s is not None:
        action_wait = float(c.wait_s)

    return base, action_wait


def convert_case_to_python_module(dsl: DslCase) -> str:
    urlmapping: List[str] = []
    urlmapping_set: Set[str] = set()

    # 收集 env/sig 的 signal_name
    for s in dsl.sets:
        for a in s.assignments:
            if a.kind == "env":
                if a.name not in urlmapping_set:
                    urlmapping_set.add(a.name)
                    urlmapping.append(a.name)
    for cid in dsl.checks_in_order:
        sig = dsl.checks[cid].signal
        if sig not in urlmapping_set:
            urlmapping_set.add(sig)
            urlmapping.append(sig)
            
    for sig in commen_signals_for_ulrmapping:
        if sig not in urlmapping_set:
            urlmapping_set.add(sig)
            urlmapping.append(sig)
            
    # print(urlmapping)

    urltests: List[Dict[str, Any]] = []

    # scenario_id -> SetScenario
    scenario_id = dsl.meta.get("scenario_id")
    if scenario_id is not None:
        try:
            sid = int(str(scenario_id).strip(), 0)
            urltests.append(
                {
                    "description": "初始化场景",
                    "steps": [{"action": "SetScenario", "scenario_id": sid}],
                }
            )
        except ValueError:
            # META 里 scenario_id 不可解析时跳过
            pass

    consumed_inline_checks: Set[str] = set()

    def emit_set_step(step: DslSetStep) -> None:
        steps: List[Dict[str, Any]] = []
        if step.dynamic_disconnect:
            steps.append(
                {
                    "action": "SetSysVar",
                    "namespace": "simulink",
                    "var_name": "dynamic_disconnect",
                    "value": 1,
                }
            )

        for a in step.assignments:
            if a.kind == "sys":
                steps.append(
                    {
                        "action": "SetSysVar",
                        "namespace": a.namespace,
                        "var_name": a.name,
                        "value": a.value,
                    }
                )
            else:
                steps.append({"action": "SetSignal", "signal": a.name, "value": a.value})

        if step.wait_s is not None:
            steps.append({"action": "Wait", "wait_time": float(step.wait_s)})

        # 使用 comment 作为 description，如果没有则使用 sid
        description = step.comment if step.comment else step.sid
        urltests.append({"description": description, "steps": steps})

        if step.then_checks:
            # 为每个 CHECK 生成独立的步骤
            for cid in step.then_checks:
                cid_u = cid.upper()
                cdef = dsl.checks.get(cid_u)
                if not cdef:
                    continue
                base, action_wait = _check_to_actions(cdef)
                steps = [base]
                if action_wait is not None:
                    steps.append({"action": "Wait", "wait_time": action_wait})
                consumed_inline_checks.add(cid_u)
                
                # 使用 CHECK 的 comment 作为 description，如果没有则使用 cid
                description = cdef.comment if cdef.comment else cid_u
                urltests.append({"description": description, "steps": steps})

    for s in dsl.sets:
        emit_set_step(s)

    # 剩余 checks（未被 then CHECK 消费）按原顺序追加
    for cid in dsl.checks_in_order:
        if cid in consumed_inline_checks:
            continue
        cdef = dsl.checks[cid]
        #print([_check_to_actions(cdef)])
        base, action_wait = _check_to_actions(cdef)

        # 使用 comment 作为 description，如果没有则使用 cid
        description = cdef.comment if cdef.comment else cid
        if action_wait is not None:
            urltests.append({"description": description, "steps": [base] + [{"action": "Wait", "wait_time": action_wait}]})
        else:
            urltests.append({"description": description, "steps": [base]})

    # print(urltests)

    # 生成 python 源码
    header_lines: List[str] = []
    header_lines.append("# -*- coding: utf-8 -*-")
    header_lines.append("# Auto-generated by dsl_case_converter.py")
    header_lines.append("")

    # 注意：按用户给的第二种格式，使用 __name__ 变量承载 case 名称
    header_lines.append(f"__name__ = {dsl.name!r}")
    header_lines.append("")

    header_lines.append(f"CaseID = {dsl.meta.get('case_id')!r}")
    header_lines.append("")

    header_lines.append(f"URLmapping = {pprint.pformat(urlmapping, width=120, sort_dicts=False)}")
    header_lines.append("")
    header_lines.append(f"URLTests = {pprint.pformat(urltests, width=120, sort_dicts=False)}")
    header_lines.append("")

    return "\n".join(header_lines)


def iter_dsl_files(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    out: List[Path] = []
    for p in root.rglob("*.dsl"):
        if p.is_file():
            out.append(p)
    return sorted(out)


def convert_one_file(input_path: Path, output_dir: Optional[Path]) -> Path:
    text = input_path.read_text(encoding="utf-8", errors="ignore")
    dsl = parse_dsl_case(text, fallback_name=input_path.stem)
    py_src = convert_case_to_python_module(dsl)

    out_dir = output_dir if output_dir is not None else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{input_path.stem}.py"
    out_path.write_text(py_src, encoding="utf-8")
    return out_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="批量把 .dsl case 转成 URLTests .py")
    parser.add_argument("--input", type=str, help="输入 .dsl 文件或目录")
    parser.add_argument("--output", type=str, default=None, help="输出目录（默认与输入文件同目录）")
    args = parser.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"输入路径不存在: {in_path}")

    out_dir = Path(args.output) if args.output else None

    dsl_files = iter_dsl_files(in_path)
    if not dsl_files:
        raise SystemExit(f"未找到 .dsl 文件: {in_path}")

    for f in dsl_files:
        out_path = convert_one_file(f, out_dir)
        print(f"Converted: {f} -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
