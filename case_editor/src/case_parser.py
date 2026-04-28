"""
DSL Parser for Canoe test cases.

This module parses a simple human-friendly DSL into a JSON-like dict
that can be fed to a test runner. The DSL supports two sections: [SET]
and [CHECK], along with case metadata and optional cross-phase inline checks.

Grammar (informal):

  CASE: <case_id> <name...>
  META: key=value key=value ...

  [SET]
  S1: set SignalA = 1 wait 200ms [then CHECK C1[,C2 ...]]
  S2: set SignalB = 0 wait 100ms
  S3: set SignalC = 3                      # 'wait' optional
  ...

  [CHECK]
  C1: check SignalX == 1 timeout 1500ms [count >= 1] [after 100ms]
  C2: check SignalY in {2,3} timeout 1000ms [count == 2]
  C3: check SignalZ in 2..5 timeout 2s [after 100ms]

Shorthand / legacy support:
  - timeout <dur>   (preferred; equivalent to legacy 'window 0..<dur>')
  - window 0..<dur>        (legacy, maps to timeout_ms)
  - window <dur>           (legacy, maps to timeout_ms)
  - window <a>..<b>        (legacy range; preserved as window_ms [a,b])
  - after <dur>            (only duration form is supported; event forms are not allowed)

Also supports the more verbose legacy forms:
  - after_detect wait_event EventName timeout 500ms
  - after_detect wait 100ms

Output (dict):
{
  "case_id": str,
  "name": str,
  "meta": dict,
  "steps": [
      {"id": "S1", "type": "set", "signal": "SignalA", "value": 1, "wait_ms": 200,
       "inline_checks": ["C1"]},
      {"id": "C1", "type": "check", "signal": "SignalX", ...}
  ],
  "phase_order": ["set", "check"],
  "flow": ["S1", "C1", "S2", ...]
}

The parser is intentionally strict about syntax but provides descriptive
errors. Durations default to milliseconds when unit is omitted. "s" is seconds.

No third-party dependencies.
"""

from __future__ import annotations

from importlib.resources import path
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any


class ParserError(Exception):
    """Raised when the DSL cannot be parsed."""


@dataclass
class ParserDefaults:
    """Holds default configuration for the parser behavior."""

    default_event_timeout_ms: int = 500


_SECTION_SET = "set"
_SECTION_CHECK = "check"


def parse_duration_to_ms(raw: str) -> int:
    """Parse a duration string into milliseconds.

    Accepts formats like:
      - "1500ms" => 1500
      - "1.5s" => 1500
      - "200" => 200 (assumed ms)

    Also accepts "us" (microseconds) and "ns" (nanoseconds) but rounds to ms.
    """

    text = raw.strip().lower()
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(ms|s|us|ns)?", text)
    if not match:
        raise ParserError(f"Invalid duration: '{raw}'")
    value = float(match.group(1))
    unit = match.group(2) or "ms"
    if unit == "ms":
        millis = value
    elif unit == "s":
        millis = value * 1000.0
    elif unit == "us":
        millis = value / 1000.0
    elif unit == "ns":
        millis = value / 1_000_000.0
    else:
        raise ParserError(f"Unsupported duration unit in '{raw}'")
    # Round to nearest integer millisecond
    return int(round(millis))


def _parse_scalar_value(raw: str) -> Any:
    """Parse a scalar token into int/float if numeric, else as string.

    For integers (e.g., "3"), returns int 3. For floats ("3.14"), returns float.
    Otherwise returns the original string (without surrounding quotes if present).
    """

    token = raw.strip()
    # Strip optional quotes
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        return token[1:-1]

    # Try int
    if re.fullmatch(r"-?\d+", token):
        try:
            return int(token)
        except ValueError:
            pass
    # Try float
    if re.fullmatch(r"-?\d+\.\d+", token):
        try:
            return float(token)
        except ValueError:
            pass

    if re.fullmatch(r"0x[0-9a-fA-F]+", token):
        try:
            return int(token, 16)
        except ValueError:
            pass
    
    raise ParserError(f"Invalid scalar value: '{raw}'")


def _split_kv_pairs(raw: str) -> Dict[str, str]:
    """Parse META key=value pairs separated by whitespace.

    Values keep their raw string (no type coercion) to stay faithful to metadata.
    """

    pairs: Dict[str, str] = {}
    text = raw.strip()
    if not text:
        return pairs
    for part in re.split(r"\s+", text):
        if not part:
            continue
        if "=" not in part:
            raise ParserError(f"META expects key=value tokens, got '{part}'")
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ParserError(f"Invalid META token '{part}' (empty key)")
        pairs[key] = value
    return pairs

def _parse_bool(raw: str) -> bool:
    """Parse a boolean value from a string."""
    text = raw.strip().lower()
    if text in {"true", "1"}:
        return True
    elif text in {"false", "0"}:
        return False
    raise ParserError(f"Invalid boolean value: '{raw}'")

def _parse_set_step(line: str) -> Tuple[Dict[str, Any], Optional[List[str]]]:
    """Parse a SET step line.

    Example:
      S2: set SignalB = 0 wait 100ms then CHECK C1,C2 comment "这是注释"

    Returns (step_dict, inline_checks or None)
    """

    # Support multiple assignments joined by '&&':
    #   S2: set SignalB = 0 && SignalD = 2 wait 100ms then CHECK C1
    m = re.fullmatch(
        r"\s*(?P<id>[Ss]\w*)\s*:\s*set\s+"
        r"(?P<assignments>.+?)"
        r"(?:\s+keepDynamic\s*(?P<keep>[^\s]+))?" # keepDynamic的作用是断开动力学，与系统变量simulink::dynamic_disconnect相关联, 没有keepDynamic字段或者keepDynamic字段为1或者true表示不断开动力学，为0或者false表示断开动力学
        r"(?:\s+wait\s*(?P<wait>[^\s]+))?"
        r"(?:\s+relLonDistance(?:\s*(?P<rel_lon_distance_op>==|>=|<=))?\s*(?P<rel_lon_distance>\S+))?"
        r"(?:\s+relLatDistance(?:\s*(?P<rel_lat_distance_op>==|>=|<=))?\s*(?P<rel_lat_distance>\S+))?"
        r"(?:\s+then\s+CHECK\s+(?P<checks>[^\s]+(?:(?!\s+comment\s+\")[^\s]*)*))?"
        r"(?:\s+comment\s+\"(?P<comment>[^\"]*)\")?"
        r"\s*",
        line,
        flags=re.IGNORECASE,
    )
    if not m:
        raise ParserError(f"Invalid SET line: '{line.strip()}'")

    step_id = m.group("id")
    assignments_raw = m.group("assignments")
    wait_raw = m.group("wait")
    checks_raw = m.group("checks")
    keep_raw = m.group("keep")
    rel_lon_distance_raw = m.group("rel_lon_distance")
    rel_lon_distance_op = m.group("rel_lon_distance_op")
    rel_lat_distance_raw = m.group("rel_lat_distance")
    rel_lat_distance_op = m.group("rel_lat_distance_op")
    comment_raw = m.group("comment")

    # Parse one or more assignments: Signal = value [&& Signal2 = value2 ...]
    assignment_parts = [part.strip() for part in re.split(r"\s*&&\s*", assignments_raw) if part.strip()]

    if not assignment_parts:
        raise ParserError(f"SET '{step_id}' missing assignments")
    assignments: List[Dict[str, Any]] = []
    for part in assignment_parts:
        #am = re.fullmatch(r"(?P<signal>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*=\s*(?P<value>[^\s]+)", part)
        am = re.fullmatch(r"(?P<signal>[^:=]+(?:::[^:=]+)*)\s*=\s*(?P<value>\S+)", part)
        if not am:
            raise ParserError(f"Invalid assignment in SET '{step_id}': '{part}' (expected 'Signal = value')")
        assignments.append({
            "signal": am.group("signal"),
            "value": _parse_scalar_value(am.group("value")),
        })

    step: Dict[str, Any] = {
        "id": step_id,
        "type": _SECTION_SET,
        # For backward compatibility, also expose single 'signal'/'value' when only one assignment
    }
    if len(assignments) == 1:
        step["signal"] = assignments[0]["signal"]
        step["value"] = assignments[0]["value"]
    step["assignments"] = assignments
    if wait_raw:
        step["wait_ms"] = parse_duration_to_ms(wait_raw)
        
    if keep_raw:
        step["keep_dynamic"] = _parse_bool(keep_raw)
        
    if rel_lon_distance_raw:
        rel_lon_distance_op = rel_lon_distance_op or "=="
        if rel_lon_distance_op not in ["==", ">=", "<="]:
            raise ParserError(f"Unsupported relative longitude distance operator: '{rel_lon_distance_op}'")
        match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(m|米)?", rel_lon_distance_raw)
        if not match:
            raise ParserError(f"Invalid duration: '{rel_lon_distance_raw}'")
        value = float(match.group(1))
        unit = match.group(2) or "m"
        if unit != "m" and unit != "米":
            raise ParserError(f"Unsupported distance unit in '{rel_lon_distance_raw}'")
        step["rel_lon_distance"] = {"op": rel_lon_distance_op, "value": value}
        
    if rel_lat_distance_raw:
        rel_lat_distance_op = rel_lat_distance_op or "=="
        if rel_lat_distance_op not in ["==", ">=", "<="]:
            raise ParserError(f"Unsupported relative latitude distance operator: '{rel_lat_distance_op}'")
        match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(m|米)?", rel_lat_distance_raw)
        if not match:
            raise ParserError(f"Invalid duration: '{rel_lat_distance_raw}'")
        value = float(match.group(1))
        unit = match.group(2) or "m"
        if unit != "m" and unit != "米":
            raise ParserError(f"Unsupported distance unit in '{rel_lat_distance_raw}'")
        step["rel_lat_distance"] = {"op": rel_lat_distance_op, "value": value}

    if comment_raw:
        step["comment"] = comment_raw

    inline_checks: Optional[List[str]] = None
    if checks_raw:
        # Split by commas or whitespace
        ids = [tok.strip() for tok in re.split(r"[\s,]+", checks_raw) if tok.strip()]
        if ids:
            inline_checks = ids
            step["inline_checks"] = ids

    return step, inline_checks


def _parse_check_assert(assert_text: str) -> Dict[str, Any]:
    """Parse the assertion portion of a CHECK line.

    Supported forms:
      - '== <value>' -> {op: 'eq', value}
      - 'in {a,b,c}' -> {op: 'in', values: [a,b,c]}
      - 'in a..b'   -> {op: 'range', min: a, max: b}
    """

    text = assert_text.strip()
    if not text:
        raise ParserError("CHECK missing assertion expression (e.g., '== 1' or 'in {2,3}')")

    # Equality: == value
    m_eq = re.fullmatch(r"==\s*(.+)", text)
    if m_eq:
        return {"op": "eq", "value": _parse_scalar_value(m_eq.group(1))}
    
    m_not_eq = re.fullmatch(r"!=\s*(.+)", text)
    if m_not_eq:
        return {"op": "neq", "value": _parse_scalar_value(m_not_eq.group(1))}

    # in {a,b,c}
    m_in_set = re.fullmatch(r"in\s*\{([^}]*)\}", text, flags=re.IGNORECASE)
    if m_in_set:
        inner = m_in_set.group(1).strip()
        values: List[Any] = []
        if inner:
            for part in inner.split(","):
                values.append(_parse_scalar_value(part))
        return {"op": "in", "values": values}

    # in a..b
    m_in_range = re.fullmatch(r"in\s*([^\.\s]+)\s*\.\.\s*([^\s]+)", text, flags=re.IGNORECASE)
    if m_in_range:
        lo_raw = m_in_range.group(1)
        hi_raw = m_in_range.group(2)
        lo = _parse_scalar_value(lo_raw)
        hi = _parse_scalar_value(hi_raw)
        # If parsed as strings but represent numbers, coerce to int/float
        def _coerce_num(x: Any) -> Any:
            if isinstance(x, (int, float)):
                return x
            if re.fullmatch(r"-?\d+", str(x)):
                return int(x)  # type: ignore[arg-type]
            if re.fullmatch(r"-?\d+\.\d+", str(x)):
                return float(x)  # type: ignore[arg-type]
            return x

        return {"op": "range", "min": _coerce_num(lo), "max": _coerce_num(hi)}

    raise ParserError(f"Unsupported assertion expression: '{assert_text}'")

import re
from typing import Any, Dict, List, Optional, Tuple
 
def _split_top_level_and(s: str) -> List[str]:
    """按顶层 && 拆分；不会在 {..} / (..) / [..] 内拆分。"""
    parts: List[str] = []
    buf: List[str] = []
    depth_curly = depth_paren = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "{":
            depth_curly += 1
        elif ch == "}":
            depth_curly = max(0, depth_curly - 1)
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
 
        if (
            ch == "&"
            and i + 1 < len(s)
            and s[i + 1] == "&"
            and depth_curly == 0
            and depth_paren == 0
        ):
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += 2
            continue
 
        buf.append(ch)
        i += 1
 
    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts
 
 
def _parse_single_check_clause(
    clause: str,
    *,
    parse_duration_to_ms,
    _parse_check_assert,
    ParserError,
) -> Dict[str, Any]:
    m = re.fullmatch(
        r"""
        \s*
        (?P<signal>[A-Za-z_][\w ]*(?:::[A-Za-z_][\w ]*)*)
        \s*
        (?P<rest>(?:==|!=|>=|<=|>|<|\bnot\s+in\b|\bin\b).+)
        \s*
        """,
        clause,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    if not m:
        raise ParserError(f"Invalid CHECK clause: '{clause.strip()}'")
 
    signal_name = m.group("signal").strip()
    rest = m.group("rest").strip()
 
    def _find_kw(s: str, kw: str) -> int:
        mm = re.search(rf"\b{kw}\b", s, flags=re.IGNORECASE)
        return mm.start() if mm else -1
 
    idx_to = _find_kw(rest, "timeout")
    idx_window = _find_kw(rest, "window")
    idx_count = _find_kw(rest, "count")
    idx_checkintime = _find_kw(rest, "duration")
    idx_wait = _find_kw(rest, "wait")
    idx_async = _find_kw(rest, "async")

    indices = [i for i in [idx_to, idx_window, idx_count, idx_checkintime, idx_wait, idx_async] if i >= 0]
    cut = min(indices) if indices else len(rest)
 
    assert_part = rest[:cut].strip()
    tail = rest[cut:].strip()
 
    if not assert_part:
        raise ParserError(f"CHECK clause for '{signal_name}' missing assertion expression")
 
    assert_dict = _parse_check_assert(assert_part)
 
    window_ms: Optional[Tuple[int, int]] = None
    timeout_ms: Optional[int] = None
    count_dict: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    wait_ms: Optional[int] = None
    is_async: Optional[bool] = None

    def _consume(regex: str, text: str, flags: int = re.IGNORECASE):
        mm = re.search(regex, text, flags)
        if not mm:
            return None, text
        start, end = mm.span()
        new_text = (text[:start] + text[end:]).strip()
        return mm, new_text
 
    m_to, tail = _consume(r"\btimeout\s+([^\s]+)", tail)
    if m_to:
        timeout_ms = parse_duration_to_ms(m_to.group(1))
 
    m_in, tail = _consume(r"\bduration\s+([^\s]+)", tail)
    if m_in:
        duration_ms = parse_duration_to_ms(m_in.group(1))

    m_async, tail = _consume(r"\basync\s+([^\s]+)", tail)
    if m_async:
        is_async = _parse_bool(m_async.group(1))

    m_wait, tail = _consume(r"\bwait\s+([^\s]+)", tail)
    if m_wait:
        wait_ms = parse_duration_to_ms(m_wait.group(1))
 
    m_win, tail = _consume(r"\bwindow\s+([^\.\s]+)\s*\.\.\s*([^\s]+)", tail)
    if m_win:
        window_ms = (parse_duration_to_ms(m_win.group(1)), parse_duration_to_ms(m_win.group(2)))
    else:
        m_win_single, tail2 = _consume(r"\bwindow\s+([^\s]+)", tail)
        if m_win_single:
            timeout_ms = parse_duration_to_ms(m_win_single.group(1))
            tail = tail2
 
    m_cnt, tail = _consume(r"\bcount\s*(==|>=|<=)\s*(\d+)", tail)
    if m_cnt:
        op = m_cnt.group(1)
        val = int(m_cnt.group(2))
        if op == "==":
            count_dict = {"exact": val}
        elif op == ">=":
            count_dict = {"min": val}
        elif op == "<=":
            count_dict = {"max": val}
        else:
            raise ParserError(f"Unsupported count operator '{op}'")
 
    tail = tail.strip()
    if tail:
        raise ParserError(f"Unrecognized tokens in CHECK clause for '{signal_name}': '{tail}'")
 
    out: Dict[str, Any] = {"signal": signal_name, "assert_h": assert_dict}
    if window_ms is not None:
        out["window_ms"] = list(window_ms)
    if timeout_ms is not None:
        out["timeoutOfCheck_ms"] = timeout_ms
    if count_dict is not None:
        out["count"] = count_dict
    if duration_ms is not None:
        out["checkInTime_ms"] = duration_ms
    if wait_ms is not None:
        out["wait_ms"] = wait_ms
    if is_async is not None:
        out["async"] = is_async
    return out
 
 
def _parse_check_step(line: str, defaults) -> Dict[str, Any]:
    m = re.fullmatch(
        r"""
        \s*(?P<id>\w+)\s*:\s*check\s+
        (?P<body>.+?)
        (?:\s+comment\s+"(?P<comment>[^"]*)")?
        \s*
        """,
        line,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    if not m:
        raise ParserError(f"Invalid CHECK line: '{line.strip()}'")

    step_id = m.group("id")
    body = m.group("body").strip()
    comment_raw = m.group("comment")

    clauses = _split_top_level_and(body)
    if not clauses:
        raise ParserError(f"CHECK '{step_id}' missing clause(s)")

    checks = [
        _parse_single_check_clause(
            c,
            parse_duration_to_ms=parse_duration_to_ms,
            _parse_check_assert=_parse_check_assert,
            ParserError=ParserError,
        )
        for c in clauses
    ]

    result = {
        "id": step_id,
        "type": _SECTION_CHECK,
        "checks": checks,
    }

    if comment_raw:
        result["comment"] = comment_raw

    return result

def _compute_flow(
    set_steps: List[Dict[str, Any]],
    check_steps: List[Dict[str, Any]],
    inline_map: Dict[str, List[str]],
) -> Tuple[List[str], List[str]]:
    """Compute the execution flow order.

    - Start with all SET steps in declared order.
    - After each SET step, inject any inline checks bound to that SET.
    - Append the remaining CHECK steps that were not inlined.
    """
    signals: Dict = {}
    flow: List[str] = []
    inlined: set[str] = set()
    
    # print(check_steps)

    check_ids_in_declared_order = [s["id"] for s in check_steps]
    signals["check"] = [chk["signal"] for s in check_steps for chk in s["checks"]]
    signals["set"] = [st["signal"] for s in set_steps for st in s["assignments"]]
    for s in set_steps:
        s_id = s["id"]
        flow.append(s_id)
        if s_id in inline_map:
            for c_id in inline_map[s_id]:
                flow.append(c_id)
                inlined.add(c_id)

    # Append non-inlined checks in their declared order
    for c_id in check_ids_in_declared_order:
        if c_id not in inlined:
            flow.append(c_id)

    return (flow, signals)


def parse_case_dsl(text: str, *, defaults: Optional[ParserDefaults] = None) -> Dict[str, Any]:
    """Parse a single case DSL string into a JSON-serializable dict.

    Raises ParserError on invalid input.
    """

    if defaults is None:
        defaults = ParserDefaults()

    lines = [ln.rstrip() for ln in text.splitlines()]

    case_id: Optional[str] = None
    case_name: Optional[str] = None
    meta: Dict[str, str] = {}

    current_section: Optional[str] = None
    set_steps: List[Dict[str, Any]] = []
    check_steps: List[Dict[str, Any]] = []
    inline_checks_map: Dict[str, List[str]] = {}

    line_num = 0
    for raw_line in lines:
        line_num += 1
        line = raw_line.strip()
        if not line:
            continue
        # Support comments starting with '#'
        if line.startswith('#'):
            continue

        # Section headers
        if re.fullmatch(r"\[\s*SET\s*\]", line, flags=re.IGNORECASE):
            current_section = _SECTION_SET
            continue
        if re.fullmatch(r"\[\s*CHECK\s*\]", line, flags=re.IGNORECASE):
            current_section = _SECTION_CHECK
            continue

        # Case header
        m_case = re.fullmatch(r"CASE:\s+(.+)", line, flags=re.IGNORECASE)
        if m_case:
            if case_id is not None:
                raise ParserError("Duplicate CASE header")
            payload = m_case.group(1).strip()
            if not payload:
                raise ParserError("CASE header requires '<case_id> <name>'")
            
            #### 可以不需要case_name了，因为case_name放到meta中成为test_point了####
            parts = payload.split(None, 1)
            if len(parts) == 1:
                case_id = parts[0]
                case_name = parts[0]
            else:
                case_id, case_name = parts[0], parts[1]
            # print(case_id, case_name)

            continue

        # Meta header
        m_meta = re.fullmatch(r"META:\s*(.*)", line, flags=re.IGNORECASE)
        if m_meta:
            pairs_text = m_meta.group(1)
            meta.update(_split_kv_pairs(pairs_text))
            continue

        # Steps
        if current_section == _SECTION_SET:
            step, inline = _parse_set_step(line)
            set_steps.append(step)
            if inline:
                inline_checks_map[step["id"]] = inline
            continue

        if current_section == _SECTION_CHECK:
            step = _parse_check_step(line, defaults)
            check_steps.append(step)
            continue
        raise ParserError(f"Unexpected content outside sections at line {line_num}: '{raw_line}'")

    if case_id is None or case_name is None:
        raise ParserError("Missing CASE header (expected 'CASE: <id> <name>')")

    # Validate inline checks exist
    all_check_ids = {s["id"] for s in check_steps}
    # print(all_check_ids)
    for set_id, check_ids in inline_checks_map.items():
        for c_id in check_ids:
            if c_id not in all_check_ids:
                raise ParserError(f"Inline CHECK '{c_id}' referenced by '{set_id}' not defined in [CHECK]")

    steps: List[Dict[str, Any]] = []
    steps.extend(set_steps)
    steps.extend(check_steps)
    
    # print(inline_checks_map)

    flow, signals = _compute_flow(set_steps, check_steps, inline_checks_map)
    meta["signals"] = signals

    result = {
        "case_id": case_id,
        "name": case_name,
        "meta": meta,
        "steps": steps,
        "phase_order": ["set", "check"],
        "flow": flow,
    }
    return result


def parse_case_file(dsl_content: str, *, defaults: Optional[ParserDefaults] = None) -> Dict[str, Any]:
    """Parse a case DSL file and return the JSON-serializable dict."""
    return parse_case_dsl(dsl_content, defaults=defaults)


def dump_case_json(obj: Dict[str, Any], *, indent: int = 2) -> str:
    """Serialize the parsed case JSON with stable formatting."""
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False)
