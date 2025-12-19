#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量将 DSL case（.dsl 文本）转换为 Python case（.py 脚本）:

DSL 示例:
  CASE: xxx
  META: test_point=... priority=... owner=... scenario_id=48 scenario_name=...
  S1: set ... && set ... wait 200ms then CHECK C1,C2
  ...
  C1: check sig::CAN 1::MSG::Signal ==3 timeoutOfCheck 1500ms wait 200ms

输出 Python 结构:
  __name__ = "xxx"
  URLmapping = [...]
  URLTests = [ {description, steps:[{action,...}, ...]}, ... ]

仅使用标准库。
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


_RE_CASE = re.compile(r"^\s*CASE:\s*(?P<name>.+?)\s*$")
_RE_META = re.compile(r"^\s*META:\s*(?P<meta>.+?)\s*$")
_RE_SLINE = re.compile(r"^\s*(?P<sid>S\d+)\s*:\s*(?P<body>.+?)\s*$")
_RE_CLINE = re.compile(r"^\s*(?P<cid>C\d+)\s*:\s*(?P<body>.+?)\s*$")

_RE_TIME = re.compile(r"^\s*(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>ms|s)\s*$", re.IGNORECASE)

# env::CAN 1::MSG::Signal 或 sig::CAN 1::MSG::Signal
_RE_BUS_SIG = re.compile(
    r"^(?P<prefix>env|sig)::CAN\s+(?P<ch>\d+)::(?P<msg>[^:]+)::(?P<sig>[^=\s]+)\s*$",
    re.IGNORECASE,
)

# sys::Namespace::Var
_RE_SYS_VAR = re.compile(
    r"^sys::(?P<ns>[^:]+)::(?P<var>[^=\s]+)\s*$",
    re.IGNORECASE,
)


class DslParseError(ValueError):
    pass


@dataclass(frozen=True)
class DslHeader:
    case_name: str
    meta: Dict[str, str]


@dataclass(frozen=True)
class DslSetStep:
    sid: str
    raw: str
    body: str


@dataclass(frozen=True)
class DslCheckDef:
    cid: str
    raw: str
    body: str


def _strip_inline_comment(line: str) -> str:
    # 仅移除以 # 开头的注释；不处理字符串内的 #。
    # DSL 示例中未说明注释语法，这里保守处理：行首/前导空白后的 # 当作注释。
    s = line.rstrip("\n")
    if re.match(r"^\s*#", s):
        return ""
    return s


def parse_meta_kv(meta_str: str) -> Dict[str, str]:
    """
    META 行是空格分隔的 key=value；value 可能包含中文、下划线、点号等。
    假设 value 中不包含未转义空格（与示例一致）。
    """
    meta: Dict[str, str] = {}
    for part in meta_str.strip().split():
        if "=" not in part:
            # 允许孤立字段，忽略
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            meta[k] = v
    return meta


def parse_time_to_seconds(time_str: str) -> float:
    m = _RE_TIME.match(time_str)
    if not m:
        raise DslParseError(f"无法解析时间: {time_str!r}")
    num = float(m.group("num"))
    unit = m.group("unit").lower()
    if unit == "ms":
        return num / 1000.0
    if unit == "s":
        return num
    raise DslParseError(f"未知时间单位: {time_str!r}")


def parse_number(value_str: str) -> Any:
    """
    解析 DSL 中 value：支持 0x..、十进制、浮点。
    解析失败则返回原字符串（保留）。
    """
    s = value_str.strip()
    if not s:
        return s
    try:
        # ast.literal_eval 支持 "0x1" 吗？不支持；所以先处理 hex
        if re.match(r"^[+-]?0x[0-9a-fA-F]+$", s):
            return int(s, 16)
        if re.match(r"^[+-]?\d+\.\d+$", s):
            return float(s)
        if re.match(r"^[+-]?\d+$", s):
            return int(s)
    except Exception:
        pass
    # 最后尝试 literal_eval（例如 "3.0"、"'abc'"）
    try:
        return ast.literal_eval(s)
    except Exception:
        return s


def sanitize_filename(name: str) -> str:
    # 将 case 名称转换为安全文件名
    s = name.strip()
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE)
    s = s.strip("_")
    return s or "case"


def read_dsl_file(path: Path) -> Tuple[DslHeader, List[DslSetStep], List[DslCheckDef]]:
    case_name: Optional[str] = None
    meta: Dict[str, str] = {}
    s_steps: List[DslSetStep] = []
    c_defs: List[DslCheckDef] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = _strip_inline_comment(raw_line).strip()
        if not line:
            continue
        m_case = _RE_CASE.match(line)
        if m_case:
            case_name = m_case.group("name").strip()
            continue
        m_meta = _RE_META.match(line)
        if m_meta:
            meta = parse_meta_kv(m_meta.group("meta"))
            continue
        m_s = _RE_SLINE.match(line)
        if m_s:
            sid = m_s.group("sid")
            body = m_s.group("body").strip()
            s_steps.append(DslSetStep(sid=sid, raw=line, body=body))
            continue
        m_c = _RE_CLINE.match(line)
        if m_c:
            cid = m_c.group("cid")
            body = m_c.group("body").strip()
            c_defs.append(DslCheckDef(cid=cid, raw=line, body=body))
            continue

        # 其他行：忽略，但保守起见可报错
        raise DslParseError(f"无法识别的行: {line!r} (file={path})")

    if not case_name:
        raise DslParseError(f"缺少 CASE 头: {path}")
    return DslHeader(case_name=case_name, meta=meta), s_steps, c_defs


def _extract_signal_name_from_bus_expr(expr: str) -> Optional[str]:
    m = _RE_BUS_SIG.match(expr.strip())
    if not m:
        return None
    return m.group("sig")


def _parse_set_target(expr: str) -> Tuple[str, Dict[str, Any]]:
    """
    返回 (kind, action_dict):
      kind: "SetSignal" 或 "SetSysVar"
      action_dict: {action:..., ...}
    """
    s = expr.strip()
    # sys::Namespace::Var
    m_sys = _RE_SYS_VAR.match(s)
    if m_sys:
        return (
            "SetSysVar",
            {
                "action": "SetSysVar",
                "namespace": m_sys.group("ns"),
                "var_name": m_sys.group("var"),
            },
        )
    # env::CAN ...
    m_bus = _RE_BUS_SIG.match(s)
    if m_bus and m_bus.group("prefix").lower() == "env":
        return (
            "SetSignal",
            {
                "action": "SetSignal",
                "signal": m_bus.group("sig"),
            },
        )
    raise DslParseError(f"无法解析 set 目标: {expr!r}")


def _parse_check_target(expr: str) -> str:
    s = expr.strip()
    m_bus = _RE_BUS_SIG.match(s)
    if not m_bus or m_bus.group("prefix").lower() != "sig":
        raise DslParseError(f"无法解析 check 目标: {expr!r}")
    return m_bus.group("sig")


def _split_then_check(body: str) -> Tuple[str, List[str]]:
    """
    将:
      "... then CHECK C1,C2"
    拆成:
      ("...", ["C1","C2"])
    """
    m = re.search(r"\bthen\s+CHECK\s+(?P<list>.+?)\s*$", body, flags=re.IGNORECASE)
    if not m:
        return body.strip(), []
    prefix = body[: m.start()].strip()
    lst = m.group("list").strip()
    # 支持逗号/空格分隔
    ids = [x.strip() for x in re.split(r"[,\s]+", lst) if x.strip()]
    return prefix, ids


def _extract_wait_token(body: str) -> Tuple[str, Optional[float]]:
    """
    从 set body 中提取 'wait <time>'，返回 (remaining, seconds or None)
    只取最后一次 wait（通常只有一次）。
    """
    # 允许：... wait 200ms
    m = re.search(r"\bwait\s+(?P<t>-?\d+(?:\.\d+)?\s*(?:ms|s))\b", body, flags=re.IGNORECASE)
    if not m:
        return body.strip(), None
    t_raw = m.group("t")
    seconds = parse_time_to_seconds(t_raw)
    remaining = (body[: m.start()] + body[m.end() :]).strip()
    return remaining, seconds


def _has_keep_dynamic_false(body: str) -> bool:
    return re.search(r"\bkeep_dynamic\s+false\b", body, flags=re.IGNORECASE) is not None


def _remove_keep_dynamic_false(body: str) -> str:
    return re.sub(r"\bkeep_dynamic\s+false\b", "", body, flags=re.IGNORECASE).strip()


def _parse_set_commands(body: str) -> List[Tuple[str, Optional[str]]]:
    """
    解析形如:
      set A=1 && set B && set C=0x1
    返回:
      [(target_expr, value_expr_or_none), ...]
    其中 target_expr 是 "sys::..::.." 或 "env::CAN ..::..::.."
    """
    parts = [p.strip() for p in body.split("&&")]
    out: List[Tuple[str, Optional[str]]] = []
    for p in parts:
        if not p:
            continue
        m = re.match(r"^set\s+(?P<rest>.+?)\s*$", p, flags=re.IGNORECASE)
        if not m:
            raise DslParseError(f"set 步骤中存在非 set 语句: {p!r}")
        rest = m.group("rest").strip()
        # 允许 "X=Y" 或只有 "X"（默认 value=1）
        if "=" in rest:
            left, right = rest.split("=", 1)
            out.append((left.strip(), right.strip()))
        else:
            out.append((rest.strip(), None))
    if not out:
        raise DslParseError(f"set 步骤为空: {body!r}")
    return out


def _parse_check_condition(body: str) -> Tuple[str, Any, str]:
    """
    解析 check 条件，返回 (signal, expected, mode)
      mode: "eq" | "in_set" | "in_range"
      expected: int/float/str 或 list
    支持:
      check sig::... == 3
      check sig::... in {2,3}
      check sig::... in 2..5
    """
    s = body.strip()
    # 兼容 "==3" / "in{2,3}" 这类无空格写法
    m = re.match(
        r"^check\s+(?P<target>.+?)\s*(?P<op>==|in)\s*(?P<rhs>.+?)\s*$",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        raise DslParseError(f"无法解析 check 语句: {body!r}")
    signal = _parse_check_target(m.group("target"))
    op = m.group("op").lower()
    rhs = m.group("rhs").strip()
    if op == "==":
        # 允许 rhs 中后续还带参数（timeoutOfCheck 等），因此这里只取第一个 token
        first = rhs.split()[0]
        return signal, parse_number(first), "eq"
    if op == "in":
        # 支持 {a,b} 或 a..b
        # 去掉后续参数
        first = rhs.split()[0]
        if first.startswith("{") and first.endswith("}"):
            inner = first[1:-1].strip()
            vals = [parse_number(x.strip()) for x in inner.split(",") if x.strip()]
            return signal, vals, "in_set"
        if ".." in first:
            a_str, b_str = first.split("..", 1)
            a = int(parse_number(a_str))
            b = int(parse_number(b_str))
            if b < a:
                a, b = b, a
            vals = list(range(a, b + 1))
            return signal, vals, "in_range"
        # 退化：in 后面是单值
        return signal, [parse_number(first)], "in_set"
    raise DslParseError(f"不支持的 check 操作符: {op!r}")


def _extract_check_opts(body: str) -> Tuple[str, Dict[str, float]]:
    """
    从 check body 中提取参数:
      timeoutOfCheck 1500ms
      checkInTime 2s
      wait 200ms
    返回 (body_without_opts, opts_seconds)
    """
    s = body.strip()
    opts: Dict[str, float] = {}

    def _pop(pattern: str, key: str, text: str) -> str:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            return text
        opts[key] = parse_time_to_seconds(m.group("t"))
        return (text[: m.start()] + text[m.end() :]).strip()

    s = _pop(r"\btimeoutOfCheck\s+(?P<t>-?\d+(?:\.\d+)?\s*(?:ms|s))\b", "timeout", s)
    s = _pop(r"\bcheckInTime\s+(?P<t>-?\d+(?:\.\d+)?\s*(?:ms|s))\b", "duration", s)
    s = _pop(r"\bwait\s+(?P<t>-?\d+(?:\.\d+)?\s*(?:ms|s))\b", "wait_time", s)
    return s, opts


def convert_check_def_to_actions(cdef: DslCheckDef) -> List[Dict[str, Any]]:
    """
    一个 Cn 定义转换为一个 action dict（CheckSignal 或 CheckDuration），
    其中 wait_time/timeout/duration 按秒写入同一个 dict（与你给的示例一致）。
    """
    body_wo_opts, opts = _extract_check_opts(cdef.body)
    signal, expected, _mode = _parse_check_condition(body_wo_opts)

    if "duration" in opts:
        act: Dict[str, Any] = {
            "action": "CheckDuration",
            "signal": signal,
            "value": expected,
            "duration": float(opts["duration"]),
        }
        if "wait_time" in opts:
            act["wait_time"] = float(opts["wait_time"])
        return [act]

    act2: Dict[str, Any] = {
        "action": "CheckSignal",
        "signal": signal,
        "value": expected,
    }
    if "timeout" in opts:
        act2["timeout"] = float(opts["timeout"])
    if "wait_time" in opts:
        act2["wait_time"] = float(opts["wait_time"])
    return [act2]


def convert_dsl_to_python_case(
    header: DslHeader,
    s_steps: Sequence[DslSetStep],
    c_defs: Sequence[DslCheckDef],
) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """
    返回:
      (case_name, URLmapping, URLTests)
    """
    c_map = {c.cid: c for c in c_defs}

    urlmapping: List[str] = []
    seen_map = set()

    def _add_mapping(sig_name: str) -> None:
        if sig_name in seen_map:
            return
        seen_map.add(sig_name)
        urlmapping.append(sig_name)

    # 先从 S 中收集 env 信号
    for s in s_steps:
        body0, _then = _split_then_check(s.body)
        body0 = _remove_keep_dynamic_false(body0)
        body0, _wait = _extract_wait_token(body0)
        for target_expr, _val_expr in _parse_set_commands(body0):
            sig = _extract_signal_name_from_bus_expr(target_expr)
            if sig:
                _add_mapping(sig)

    # 再从 C 中收集 sig 信号
    for c in c_defs:
        body_wo_opts, _opts = _extract_check_opts(c.body)
        # 只为确保能解析并拿到 signal
        m = re.match(
            r"^check\s+(?P<target>.+?)\s*(?P<op>==|in)\s*(?P<rhs>.+?)\s*$",
            body_wo_opts.strip(),
            flags=re.IGNORECASE,
        )
        if m:
            sig_name = _parse_check_target(m.group("target"))
            _add_mapping(sig_name)

    urltests: List[Dict[str, Any]] = []

    # META 中 scenario_id -> SetScenario
    scenario_id = header.meta.get("scenario_id")
    if scenario_id is not None:
        try:
            sid_int = int(parse_number(scenario_id))
        except Exception:
            sid_int = int(scenario_id)
        urltests.append(
            {
                "description": "初始化场景",
                "steps": [{"action": "SetScenario", "scenario_id": sid_int}],
            }
        )

    referenced_checks: List[str] = []
    referenced_set = set()
    for s in s_steps:
        _, then_ids = _split_then_check(s.body)
        for cid in then_ids:
            if cid not in referenced_set:
                referenced_set.add(cid)
                referenced_checks.append(cid)

    # 按执行顺序生成：S1..Sn（含 then CHECK 内联），最后补上未被 then 引用的 C
    executed_cids = set()
    for s in s_steps:
        body_no_then, then_ids = _split_then_check(s.body)
        keep_dyn = _has_keep_dynamic_false(body_no_then)
        body_no_then = _remove_keep_dynamic_false(body_no_then)
        body_no_then, wait_sec = _extract_wait_token(body_no_then)

        set_cmds = _parse_set_commands(body_no_then)
        actions: List[Dict[str, Any]] = []

        if keep_dyn:
            # 你要求的：必须在 set 之前
            actions.append(
                {
                    "action": "SetSysVar",
                    "namespace": "simulink",
                    "var_name": "dynamic_disconnect",
                    "value": 1,
                }
            )

        for target_expr, val_expr in set_cmds:
            _kind, base = _parse_set_target(target_expr)
            if val_expr is None:
                value = 1
            else:
                value = parse_number(val_expr)
            base["value"] = value
            actions.append(base)

        if wait_sec is not None:
            actions.append({"action": "Wait", "wait_time": float(wait_sec)})

        # then CHECK: 立即插入对应 C 动作
        for cid in then_ids:
            if cid not in c_map:
                raise DslParseError(f"{s.sid} 引用了不存在的检查 {cid}")
            actions.extend(convert_check_def_to_actions(c_map[cid]))
            executed_cids.add(cid)

        urltests.append({"description": f"{s.sid}", "steps": actions})

    # 末尾补齐未执行的 C
    for c in c_defs:
        if c.cid in executed_cids:
            continue
        urltests.append({"description": f"{c.cid}", "steps": convert_check_def_to_actions(c)})

    return header.case_name, urlmapping, urltests


def format_python_case(case_name: str, urlmapping: List[str], urltests: List[Dict[str, Any]], meta: Dict[str, str]) -> str:
    # 用 repr 输出，保证可直接执行/导入
    lines: List[str] = []
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# 本文件由 dsl_to_py_case.py 自动生成，请勿手工编辑。")
    if meta:
        # 保留 meta 作为注释，便于追溯
        meta_flat = " ".join([f"{k}={v}" for k, v in meta.items()])
        lines.append(f"# META: {meta_flat}")
    lines.append("")
    lines.append(f'__name__ = {case_name!r}')
    lines.append(f"URLmapping = {repr(urlmapping)}")
    lines.append("")
    lines.append(f"URLTests = {repr(urltests)}")
    lines.append("")
    return "\n".join(lines)


def iter_dsl_files(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted([p for p in input_path.rglob("*.dsl") if p.is_file()])
    raise FileNotFoundError(str(input_path))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="批量将 .dsl case 转换为 Python case 脚本")
    ap.add_argument("input", help="输入 .dsl 文件或目录（递归查找 *.dsl）")
    ap.add_argument(
        "-o",
        "--out-dir",
        default="converted_cases",
        help="输出目录（默认: converted_cases）",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="若输出文件已存在则覆盖",
    )
    args = ap.parse_args(argv)

    in_path = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dsl_files = iter_dsl_files(in_path)
    if not dsl_files:
        raise SystemExit(f"未找到 .dsl 文件: {in_path}")

    for dsl in dsl_files:
        header, s_steps, c_defs = read_dsl_file(dsl)
        case_name, mapping, tests = convert_dsl_to_python_case(header, s_steps, c_defs)
        py_text = format_python_case(case_name, mapping, tests, header.meta)

        out_name = sanitize_filename(case_name) + ".py"
        out_path = out_dir / out_name
        if out_path.exists() and not args.overwrite:
            raise SystemExit(f"输出已存在（可加 --overwrite）: {out_path}")
        out_path.write_text(py_text, encoding="utf-8")

    print(f"转换完成: {len(dsl_files)} 个文件 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

