"""
DSL Parser for Canoe test cases.

This module parses a simple human-friendly DSL into a JSON-like dict
that can be fed to a test runner. The DSL supports two sections: [SET]
and [CHECK], along with case metadata and optional cross-phase inline checks.

Grammar (informal):

  CASE: <case_id> <name...>
  META: key=value key=value ...

  [SET]
  S1: set SignalA = 1 within 200ms [then CHECK C1[,C2 ...]]
  S2: set SignalB = 0 within 100ms
  ...

  [CHECK]
  C1: check SignalX == 1 window 0..1500ms [count >= 1] [after 100ms]
  C2: check SignalY in {2,3} window 200..1000ms [count == 2]
  C3: check SignalZ in 2..5 window 0..2s [after EventReady@500ms]

Shorthand:
  - window <dur>   (equivalent to window 0..<dur>)

Also supports the more verbose legacy forms:
  - after_detect wait_event EventName timeout 500ms
  - after_detect wait 100ms

Output (dict):
{
  "case_id": str,
  "name": str,
  "meta": dict,
  "steps": [
      {"id": "S1", "type": "set", "signal": "SignalA", "value": 1, "within_ms": 200,
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

    return token


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


def _parse_set_step(line: str) -> Tuple[Dict[str, Any], Optional[List[str]]]:
    """Parse a SET step line.

    Example:
      S2: set SignalB = 0 within 100ms then CHECK C1,C2

    Returns (step_dict, inline_checks or None)
    """

    m = re.fullmatch(
        r"\s*(?P<id>\w+)\s*:\s*set\s+"
        r"(?P<signal>[A-Za-z_]\w*)\s*=\s*(?P<value>[^\s]+)\s+"
        r"within\s+(?P<within>[^\s]+)"
        r"(?:\s+then\s+CHECK\s+(?P<checks>.+))?\s*",
        line,
        flags=re.IGNORECASE,
    )
    if not m:
        raise ParserError(f"Invalid SET line: '{line.strip()}'")

    step_id = m.group("id")
    signal_name = m.group("signal")
    value_raw = m.group("value")
    within_raw = m.group("within")
    checks_raw = m.group("checks")

    step: Dict[str, Any] = {
        "id": step_id,
        "type": _SECTION_SET,
        "signal": signal_name,
        "value": _parse_scalar_value(value_raw),
        "within_ms": parse_duration_to_ms(within_raw),
    }

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


def _parse_check_step(line: str, defaults: ParserDefaults) -> Dict[str, Any]:
    """Parse a CHECK step line.

    Example (compact):
      C1: check SignalX == 1 window 0..1500ms count >= 1 after EventReady@500ms
      C2: check SignalY in {2,3} window 200..1000ms after 100ms
      C3: check SignalZ in 2..5 window 0..2s

    Also supports legacy verbose 'after_detect' forms.
    """

    m = re.fullmatch(r"\s*(?P<id>\w+)\s*:\s*check\s+(?P<signal>[A-Za-z_]\w*)\s+(?P<rest>.+)\s*",
                      line, flags=re.IGNORECASE)
    if not m:
        raise ParserError(f"Invalid CHECK line: '{line.strip()}'")

    step_id = m.group("id")
    signal_name = m.group("signal")
    rest = m.group("rest").strip()

    # Identify slices by keywords: window, after/after_detect, count
    # We search case-insensitively and then slice by the earliest occurrence.
    def _find_kw(s: str, kw: str) -> int:
        match = re.search(rf"\b{kw}\b", s, flags=re.IGNORECASE)
        return match.start() if match else -1

    idx_window = _find_kw(rest, "window")
    idx_after_detect = _find_kw(rest, "after_detect")
    idx_after = _find_kw(rest, "after")
    idx_count = _find_kw(rest, "count")

    indices = [i for i in [idx_window, idx_after_detect, idx_after, idx_count] if i >= 0]
    cut = min(indices) if indices else len(rest)
    assert_part = rest[:cut].strip()
    tail = rest[cut:].strip()

    if not assert_part:
        raise ParserError(f"CHECK '{step_id}' missing assertion expression")
    assert_dict = _parse_check_assert(assert_part)

    window_ms: Optional[Tuple[int, int]] = None
    after_dict: Optional[Dict[str, Any]] = None
    count_dict: Optional[Dict[str, Any]] = None

    # Parse remaining attributes in any order
    # We'll iteratively consume known patterns until tail stabilizes or becomes empty
    def _consume(regex: str, text: str, flags: int = re.IGNORECASE) -> Tuple[Optional[re.Match[str]], str]:
        m = re.search(regex, text, flags)
        if not m:
            return None, text
        start, end = m.span()
        new_text = (text[:start] + text[end:]).strip()
        return m, new_text

    # window a..b (durations)
    m_win, tail = _consume(r"\bwindow\s+([^\.\s]+)\s*\.\.\s*([^\s]+)", tail)
    if m_win:
        start_raw = m_win.group(1)
        end_raw = m_win.group(2)
        window_ms = (parse_duration_to_ms(start_raw), parse_duration_to_ms(end_raw))
    else:
        # window <dur>  -> [0, dur]
        m_win_single, tail2 = _consume(r"\bwindow\s+([^\s]+)", tail)
        if m_win_single:
            end_raw = m_win_single.group(1)
            window_ms = (0, parse_duration_to_ms(end_raw))
            tail = tail2

    # count operator value
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

    # after (compact forms)
    #  - after 100ms
    #  - after EventReady@500ms  (default timeout if missing)
    m_after_sleep, tail2 = _consume(r"\bafter\s+(\d+(?:\.\d+)?(?:ms|s)?)\b", tail)
    if m_after_sleep:
        after_dict = {"type": "sleep", "ms": parse_duration_to_ms(m_after_sleep.group(1))}
        tail = tail2
    else:
        m_after_event, tail2 = _consume(r"\bafter\s+([A-Za-z_]\w*)(?:@([^\s]+))?\b", tail)
        if m_after_event:
            event_name = m_after_event.group(1)
            timeout_raw = m_after_event.group(2)
            timeout_ms = (
                parse_duration_to_ms(timeout_raw)
                if timeout_raw
                else defaults.default_event_timeout_ms
            )
            after_dict = {"type": "event", "name": event_name, "timeout_ms": timeout_ms}
            tail = tail2

    # after_detect legacy forms
    if re.search(r"\bafter_detect\b", tail, flags=re.IGNORECASE):
        # after_detect wait_event <Event> timeout <dur>
        m_legacy_event, tail = _consume(
            r"\bafter_detect\s+wait_event\s+([A-Za-z_]\w*)\s+timeout\s+([^\s]+)",
            tail,
        )
        if m_legacy_event:
            after_dict = {
                "type": "event",
                "name": m_legacy_event.group(1),
                "timeout_ms": parse_duration_to_ms(m_legacy_event.group(2)),
            }
        else:
            # after_detect wait <dur>
            m_legacy_sleep, tail = _consume(r"\bafter_detect\s+wait\s+([^\s]+)", tail)
            if m_legacy_sleep:
                after_dict = {"type": "sleep", "ms": parse_duration_to_ms(m_legacy_sleep.group(1))}

    tail = tail.strip()
    if tail:
        # If any unexpected residue, raise a clear error
        raise ParserError(f"Unrecognized tokens in CHECK '{step_id}': '{tail}'")

    step: Dict[str, Any] = {
        "id": step_id,
        "type": _SECTION_CHECK,
        "signal": signal_name,
        "assert": assert_dict,
    }
    if window_ms is not None:
        step["window_ms"] = list(window_ms)
    if after_dict is not None:
        step["after_detect"] = after_dict
    if count_dict is not None:
        step["count"] = count_dict

    return step


def _compute_flow(
    set_steps: List[Dict[str, Any]],
    check_steps: List[Dict[str, Any]],
    inline_map: Dict[str, List[str]],
) -> List[str]:
    """Compute the execution flow order.

    - Start with all SET steps in declared order.
    - After each SET step, inject any inline checks bound to that SET.
    - Append the remaining CHECK steps that were not inlined.
    """

    flow: List[str] = []
    inlined: set[str] = set()
    check_ids_in_declared_order = [s["id"] for s in check_steps]

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

    return flow


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
            parts = payload.split(None, 1)
            if len(parts) == 1:
                case_id = parts[0]
                case_name = parts[0]
            else:
                case_id, case_name = parts[0], parts[1]
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
    for set_id, check_ids in inline_checks_map.items():
        for c_id in check_ids:
            if c_id not in all_check_ids:
                raise ParserError(f"Inline CHECK '{c_id}' referenced by '{set_id}' not defined in [CHECK]")

    steps: List[Dict[str, Any]] = []
    steps.extend(set_steps)
    steps.extend(check_steps)

    flow = _compute_flow(set_steps, check_steps, inline_checks_map)

    result = {
        "case_id": case_id,
        "name": case_name,
        "meta": meta,
        "steps": steps,
        "phase_order": ["set", "check"],
        "flow": flow,
    }
    return result


def parse_case_file(path: str, *, defaults: Optional[ParserDefaults] = None) -> Dict[str, Any]:
    """Parse a case DSL file and return the JSON-serializable dict."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_case_dsl(text, defaults=defaults)


def dump_case_json(obj: Dict[str, Any], *, indent: int = 2) -> str:
    """Serialize the parsed case JSON with stable formatting."""
    return json.dumps(obj, ensure_ascii=False, indent=indent, sort_keys=False)

