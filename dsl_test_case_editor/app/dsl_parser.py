import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .models import Diagnostic


_CASE_RE = re.compile(r"^\s*CASE\s*:\s*(?P<name>.+?)\s*$", re.IGNORECASE)
_META_RE = re.compile(r"^\s*META\s*:\s*(?P<meta>.+?)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*\[(SET|CHECK)\]\s*$", re.IGNORECASE)

_SET_RE = re.compile(
    r"^\s*(S\d+)\s*:\s*set\s+(?P<target>.+?)\s*=\s*(?P<value>\S+)(?P<rest>.*)$",
    re.IGNORECASE,
)

_CHECK_RE = re.compile(
    r"^\s*(C\d+)\s*:\s*check\s+(?P<expr>.+)$",
    re.IGNORECASE,
)

_TARGET_RE = re.compile(
    r"^(?P<kind>sys)::(?P<path>[A-Za-z0-9_:]+)$"
    r"|^(?P<kind2>env|sig)::CAN\s+(?P<channel>\d+)::(?P<msg>[^:]+)::(?P<sig>[^:]+)$",
    re.IGNORECASE,
)

_SET_WAIT_RE = re.compile(r"\bwait\s+(?P<ms>\d+)\s*ms\b", re.IGNORECASE)
_SET_THEN_RE = re.compile(r"\bthen\s+check\s+(?P<checks>[C0-9,\s]+)\b", re.IGNORECASE)
_SET_KEEP_RE = re.compile(r"\bkeep_dynamic\s+(?P<value>true|false)\b", re.IGNORECASE)

_CHECK_EXPR_RE = re.compile(
    r"^(?P<target>.+?)\s*==\s*(?P<value>\S+)\s*(?P<rest>.*)$"
)
_CHECK_OPTION_RE = re.compile(
    r"\b(wait|timeout|timeoutOfCheck|checkInTime|duration|count|async)\s+(\S+)\b",
    re.IGNORECASE,
)


@dataclass
class _SetEntry:
    step_id: str
    line: int
    then_checks: List[str]
    target: Optional[str]
    channel: Optional[int]


@dataclass
class _CheckEntry:
    step_id: str
    line: int
    targets: List[Tuple[str, Optional[int]]]


def validate_dsl(text: str, mapping: Dict[str, int]) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    lines = text.splitlines()
    if not lines:
        diagnostics.append(_diag(1, "error", "Empty DSL content."))
        return diagnostics

    case_line = _find_first_match(lines, _CASE_RE)
    if case_line is None:
        diagnostics.append(_diag(1, "error", "CASE line is required."))

    meta_line = _find_first_match(lines, _META_RE)
    if meta_line is None:
        diagnostics.append(_diag(1, "warning", "META line is missing."))

    sections = _find_sections(lines)
    if "SET" not in sections:
        diagnostics.append(_diag(1, "error", "[SET] section is missing."))
    if "CHECK" not in sections:
        diagnostics.append(_diag(1, "error", "[CHECK] section is missing."))
    if "SET" in sections and "CHECK" in sections:
        if sections["SET"] > sections["CHECK"]:
            diagnostics.append(
                _diag(sections["SET"] + 1, "error", "[SET] must appear before [CHECK].")
            )

    set_entries: List[_SetEntry] = []
    check_entries: List[_CheckEntry] = []
    if "SET" in sections and "CHECK" in sections:
        set_entries = _parse_set_section(lines, sections, diagnostics)
        check_entries = _parse_check_section(lines, sections, diagnostics)

    _validate_then_checks(set_entries, check_entries, diagnostics)
    _validate_channels(set_entries, check_entries, mapping, diagnostics)
    _validate_duplicate_steps(set_entries, check_entries, diagnostics)

    return diagnostics


def _find_first_match(lines: List[str], pattern: re.Pattern) -> Optional[int]:
    for index, line in enumerate(lines):
        if pattern.match(line):
            return index
    return None


def _find_sections(lines: List[str]) -> Dict[str, int]:
    sections: Dict[str, int] = {}
    for index, line in enumerate(lines):
        match = _SECTION_RE.match(line)
        if match:
            sections[match.group(1).upper()] = index
    return sections


def _parse_set_section(
    lines: List[str], sections: Dict[str, int], diagnostics: List[Diagnostic]
) -> List[_SetEntry]:
    start = sections["SET"] + 1
    end = sections.get("CHECK", len(lines))
    entries: List[_SetEntry] = []
    for index in range(start, end):
        line = lines[index].strip()
        if not line:
            continue
        match = _SET_RE.match(lines[index])
        if not match:
            diagnostics.append(
                _diag(index + 1, "warning", "Unrecognized SET line format.")
            )
            continue
        step_id = match.group(1).upper()
        target = match.group("target").strip()
        channel = _extract_channel(target)
        then_checks = _parse_then_checks(match.group("rest"))
        _validate_set_options(match.group("rest"), index, diagnostics)
        entries.append(
            _SetEntry(
                step_id=step_id,
                line=index + 1,
                then_checks=then_checks,
                target=target,
                channel=channel,
            )
        )
    return entries


def _parse_then_checks(rest: str) -> List[str]:
    match = _SET_THEN_RE.search(rest)
    if not match:
        return []
    raw = match.group("checks")
    items = re.split(r"[,\s]+", raw.strip())
    return [item.strip().upper() for item in items if item.strip()]


def _validate_set_options(rest: str, index: int, diagnostics: List[Diagnostic]) -> None:
    if "wait" in rest.lower() and not _SET_WAIT_RE.search(rest):
        diagnostics.append(_diag(index + 1, "warning", "SET wait option is invalid."))
    if "keep_dynamic" in rest.lower() and not _SET_KEEP_RE.search(rest):
        diagnostics.append(
            _diag(index + 1, "warning", "SET keep_dynamic option is invalid.")
        )


def _parse_check_section(
    lines: List[str], sections: Dict[str, int], diagnostics: List[Diagnostic]
) -> List[_CheckEntry]:
    start = sections["CHECK"] + 1
    entries: List[_CheckEntry] = []
    for index in range(start, len(lines)):
        line = lines[index].strip()
        if not line:
            continue
        match = _CHECK_RE.match(lines[index])
        if not match:
            diagnostics.append(
                _diag(index + 1, "warning", "Unrecognized CHECK line format.")
            )
            continue
        step_id = match.group(1).upper()
        expr = match.group("expr")
        targets = _parse_check_expr(expr, index, diagnostics)
        entries.append(_CheckEntry(step_id=step_id, line=index + 1, targets=targets))
    return entries


def _parse_check_expr(
    expr: str, index: int, diagnostics: List[Diagnostic]
) -> List[Tuple[str, Optional[int]]]:
    results: List[Tuple[str, Optional[int]]] = []
    for part in expr.split("&&"):
        part = part.strip()
        if not part:
            continue
        match = _CHECK_EXPR_RE.match(part)
        if not match:
            diagnostics.append(
                _diag(index + 1, "warning", "CHECK expression is invalid.")
            )
            continue
        target = match.group("target").strip()
        if not _TARGET_RE.match(target):
            diagnostics.append(
                _diag(index + 1, "warning", f"Unknown target format: {target}")
            )
        channel = _extract_channel(target)
        _validate_check_options(match.group("rest"), index, diagnostics)
        results.append((target, channel))
    return results


def _validate_check_options(rest: str, index: int, diagnostics: List[Diagnostic]) -> None:
    if not rest:
        return
    for token in rest.split():
        if token.lower() in {"wait", "timeout", "timeoutofcheck", "checkintime", "duration", "count", "async"}:
            break
    if "async" in rest.lower():
        if not _CHECK_OPTION_RE.search(rest):
            diagnostics.append(
                _diag(index + 1, "warning", "CHECK async option is invalid.")
            )


def _validate_then_checks(
    set_entries: Iterable[_SetEntry],
    check_entries: Iterable[_CheckEntry],
    diagnostics: List[Diagnostic],
) -> None:
    check_ids = {entry.step_id for entry in check_entries}
    for entry in set_entries:
        for ref in entry.then_checks:
            if ref not in check_ids:
                diagnostics.append(
                    _diag(entry.line, "error", f"SET references missing CHECK step {ref}.")
                )


def _validate_channels(
    set_entries: Iterable[_SetEntry],
    check_entries: Iterable[_CheckEntry],
    mapping: Dict[str, int],
    diagnostics: List[Diagnostic],
) -> None:
    if not mapping:
        return
    available = set(mapping.values())
    for entry in set_entries:
        if entry.channel is not None and entry.channel not in available:
            diagnostics.append(
                _diag(entry.line, "warning", f"SET channel {entry.channel} is not mapped.")
            )
    for entry in check_entries:
        for _, channel in entry.targets:
            if channel is not None and channel not in available:
                diagnostics.append(
                    _diag(entry.line, "warning", f"CHECK channel {channel} is not mapped.")
                )


def _validate_duplicate_steps(
    set_entries: Iterable[_SetEntry],
    check_entries: Iterable[_CheckEntry],
    diagnostics: List[Diagnostic],
) -> None:
    set_ids: Set[str] = set()
    for entry in set_entries:
        if entry.step_id in set_ids:
            diagnostics.append(
                _diag(entry.line, "warning", f"Duplicate SET step {entry.step_id}.")
            )
        set_ids.add(entry.step_id)

    check_ids: Set[str] = set()
    for entry in check_entries:
        if entry.step_id in check_ids:
            diagnostics.append(
                _diag(entry.line, "warning", f"Duplicate CHECK step {entry.step_id}.")
            )
        check_ids.add(entry.step_id)


def _extract_channel(target: str) -> Optional[int]:
    match = _TARGET_RE.match(target)
    if not match:
        return None
    channel = match.group("channel")
    return int(channel) if channel is not None else None


def _diag(line: int, severity: str, message: str) -> Diagnostic:
    return Diagnostic(line=line, severity=severity, message=message)
