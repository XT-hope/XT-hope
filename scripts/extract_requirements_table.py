#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
import csv
from pathlib import Path
from typing import List, Tuple, Optional, Dict

Heading = Dict[str, Optional[str]]

HEADING_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)+)\s+(?P<title>.*?)(?:【(?P<id>[^】]+)】)?\s*$")


def strip_braces(text: str) -> str:
    # Remove curly brace characters only; keep inner content
    return text.replace("{", "").replace("}", "")


def strip_brackets_pair(text: str) -> str:
    # Remove the Chinese brackets section 【...】 entirely
    return re.sub(r"【[^】]*】", "", text)


def normalize_text(text: str) -> str:
    text = text.strip()
    text = strip_brackets_pair(text)
    text = strip_braces(text)
    # Normalize inner whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_heading(line: str) -> Optional[Heading]:
    m = HEADING_RE.match(line.strip())
    if not m:
        return None
    num = m.group("num")
    title = m.group("title").strip()
    req_id = m.group("id")
    return {"num": num, "title": title, "id": req_id}


def heading_level(heading_num: str) -> int:
    return len(heading_num.split("."))


def split_conditions_by_or(cond: str) -> List[str]:
    # Split by the whole word 'or' (case-insensitive) with word boundaries
    parts = re.split(r"\bor\b", cond, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


BRANCH_HEADER_RE = re.compile(r"^\s*\d+\.\s*(以下条件同时满足|以下条件满足其一)\s*[:：]?\s*$")
SUBITEM_RE = re.compile(r"^\s{2,}\d+\.\s*(.+)$")


def parse_conditions(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    Parse conditions between IF and THEN, supporting nested groups like:
    顶层：以下条件满足其一 -> 多个分支；每个分支：以下条件同时满足 -> 多条明细。
    Returns (conditions_str, next_index_position_at_THEN_line)
    """
    def parse_nested(i: int, top_agg: Optional[str]) -> Tuple[str, int]:
        branches: List[str] = []
        while i < len(lines):
            line = lines[i].rstrip("\n")
            if line.strip().startswith("THEN"):
                break
            # New branch header like "  1. 以下条件同时满足：" or "  2. ..."
            if BRANCH_HEADER_RE.match(line):
                # Determine branch aggregator by header phrase
                phrase = "以下条件同时满足" if "以下条件同时满足" in line else "以下条件满足其一"
                branch_agg = "&&" if phrase == "以下条件同时满足" else "||"
                i += 1
                # Collect subitems: accept either deeper-indented numbered lines or plain indented content
                subitems: List[str] = []
                while i < len(lines):
                    sub_line = lines[i].rstrip("\n")
                    if sub_line.strip().startswith("THEN"):
                        break
                    # Another branch header encountered -> end current branch
                    if BRANCH_HEADER_RE.match(sub_line):
                        break
                    # Accept lines starting with N. or with at least two leading spaces
                    m_sub = SUBITEM_RE.match(sub_line)
                    if not m_sub:
                        # treat indented non-empty lines as part of this branch block (e.g., without numbering)
                        if re.match(r"^\s{2,}\S", sub_line):
                            item = sub_line.strip()
                            parts = split_conditions_by_or(item)
                            if len(parts) > 1:
                                subitems.append(" || ".join(parts))
                            else:
                                subitems.append(item)
                            i += 1
                            continue
                        # blank line inside branch
                        if not sub_line.strip():
                            i += 1
                            continue
                        # plain non-indented -> branch ends
                        break
                    item = m_sub.group(1).strip()
                    parts = split_conditions_by_or(item)
                    if len(parts) > 1:
                        subitems.append(" || ".join(parts))
                    else:
                        subitems.append(item)
                    i += 1
                # Join subitems by branch aggregator and wrap parentheses
                if subitems:
                    branches.append(f"({f' {branch_agg} '.join(subitems)})")
                else:
                    branches.append("")
                continue
            # Non-branch header lines
            if not line.strip():
                i += 1
                continue
            # Stop if we hit something that clearly ends IF block
            if HEADING_RE.match(line.strip()):
                break
            if re.match(r"^\s*[CB]平台", line) or re.match(r"^\s*\{?FSM_index", line):
                break
            # If we encounter a plain numbered condition under top-level aggregator (fallback)
            m_plain = re.match(r"^\s*\d+\.\s*(.*)$", line)
            if m_plain:
                item = m_plain.group(1).strip()
                parts = split_conditions_by_or(item)
                if len(parts) > 1:
                    branches.append("(" + " || ".join(parts) + ")")
                else:
                    branches.append(item)
                i += 1
                continue
            # Otherwise stop to avoid looping
            break
        # Compose top-level joiner
        joiner = top_agg if top_agg else " && "
        cond = f" {joiner} ".join([b for b in branches if b])
        return cond, i

    aggregator: Optional[str] = None  # '&&' or '||'
    collected: List[str] = []

    i = start_idx
    # Peek for nested top guidance
    # Skip blanks
    j = i
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and ("以下条件同时满足" in lines[j] or "以下条件满足其一" in lines[j]):
        aggregator = "&&" if "以下条件同时满足" in lines[j] else "||"
        j += 1
        # If the next significant line is a branch header, use nested parsing
        k = j
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and BRANCH_HEADER_RE.match(lines[k]):
            cond_str, idx_after = parse_nested(k, aggregator)
            # Advance to THEN (or where nested parsing stopped)
            # Move i to the position where parse_results expects THEN
            # Continue scanning until we hit THEN or stop condition
            mpos = idx_after
            while mpos < len(lines) and not lines[mpos].strip().startswith("THEN"):
                if lines[mpos].strip() == "IF":
                    break
                if HEADING_RE.match(lines[mpos].strip()):
                    break
                mpos += 1
            return cond_str, mpos
        # Otherwise fall back to flat parse with set aggregator
        aggregator_set = aggregator
        i = j
    else:
        aggregator_set = None

    # Flat parse (legacy + grouped branch headers)
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if not line.strip():
            i += 1
            continue
        # Stop at THEN
        if line.strip().startswith("THEN"):
            break

        # If we encounter a numbered branch header inside flat parse, treat it as a grouped subgroup
        if BRANCH_HEADER_RE.match(line):
            phrase = "以下条件同时满足" if "以下条件同时满足" in line else "以下条件满足其一"
            subgroup_agg = "&&" if phrase == "以下条件同时满足" else "||"
            i += 1
            subitems: List[str] = []
            while i < len(lines):
                sub_line = lines[i].rstrip("\n")
                if sub_line.strip().startswith("THEN"):
                    break
                if BRANCH_HEADER_RE.match(sub_line):
                    break
                m_sub = SUBITEM_RE.match(sub_line)
                if not m_sub:
                    if re.match(r"^\s{2,}\S", sub_line):
                        item = sub_line.strip()
                        parts = split_conditions_by_or(item)
                        if len(parts) > 1:
                            subitems.append(" || ".join(parts))
                        else:
                            subitems.append(item)
                        i += 1
                        continue
                    if not sub_line.strip():
                        i += 1
                        continue
                    break
                item = m_sub.group(1).strip()
                parts = split_conditions_by_or(item)
                if len(parts) > 1:
                    subitems.append(" || ".join(parts))
                else:
                    subitems.append(item)
                i += 1
            if subitems:
                collected.append(f"({f' {subgroup_agg} '.join(subitems)})")
                continue

        # Recognize guidance lines
        if "以下条件同时满足" in line:
            aggregator_set = "&&"
            i += 1
            continue
        if "以下条件满足其一" in line:
            # Do not flip the global aggregator here; a standalone guidance line should be followed by a subgroup
            # If such line appears without numbering, try to parse the following indented items into a subgroup
            lookahead = i + 1
            subitems: List[str] = []
            while lookahead < len(lines):
                la_line = lines[lookahead].rstrip("\n")
                if la_line.strip().startswith("THEN"):
                    break
                if BRANCH_HEADER_RE.match(la_line):
                    break
                m_la = SUBITEM_RE.match(la_line)
                if not m_la:
                    if re.match(r"^\s{2,}\S", la_line):
                        item = la_line.strip()
                        parts = split_conditions_by_or(item)
                        subitems.append(" || ".join(parts) if len(parts) > 1 else item)
                        lookahead += 1
                        continue
                    if not la_line.strip():
                        lookahead += 1
                        continue
                    break
                item = m_la.group(1).strip()
                parts = split_conditions_by_or(item)
                subitems.append(" || ".join(parts) if len(parts) > 1 else item)
                lookahead += 1
            if subitems:
                collected.append(f"({f' || '.join(subitems)})")
                i = lookahead
                continue
            # If no subitems found, just set aggregator to OR for safety
            aggregator_set = "||"
            i += 1
            continue

        # Remove numbering like '1. ' or '2. '
        m = re.match(r"^\s*\d+\.\s*(.*)$", line)
        if m:
            item = m.group(1).strip()
        else:
            # Regular condition line
            item = line.strip()

        if item:
            parts = split_conditions_by_or(item)
            if len(parts) > 1:
                collected.append(" || ".join(parts))
            else:
                collected.append(item)
        i += 1

    if not collected:
        cond_str = ""
    else:
        joiner = aggregator_set if aggregator_set else " && "
        cond_str = joiner.join(collected)

    return cond_str, i  # i at THEN line index


def parse_results(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    Parse expected results under THEN and optional ELSE, until the next heading-like line or blank section separator.
    Returns (results_str, next_index_after_block)
    """
    results_then: List[str] = []
    results_else: List[str] = []

    i = start_idx

    # Current section: 'THEN' or 'ELSE'
    current = None

    def should_stop(line: str) -> bool:
        if not line.strip():
            return False  # allow sparse blanks
        if HEADING_RE.match(line.strip()):
            return True
        if re.match(r"^\s*[CB]平台", line):
            return True
        if re.match(r"^\s*\{?FSM_index", line):
            return True
        # Stop on new IF starting another block
        if line.strip() == "IF":
            return True
        return False

    while i < len(lines):
        line = lines[i].rstrip("\n")

        if should_stop(line):
            break

        if line.strip().startswith("THEN"):
            current = "THEN"
            i += 1
            continue
        if line.strip().startswith("ELSE"):
            current = "ELSE"
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        # Capture meaningful content lines
        m = re.match(r"^\s*\d+\.\s*(.*)$", line)
        item = m.group(1).strip() if m else line.strip()

        if current == "ELSE":
            results_else.append(item)
        else:
            # default to THEN if current not explicitly set yet
            results_then.append(item)
        i += 1

    # Compose result string
    def join_items(items: List[str]) -> str:
        items = [s for s in (x.strip() for x in items) if s]
        return " && ".join(items)

    then_str = join_items(results_then)
    else_str = join_items(results_else)

    if then_str and else_str:
        out = f"{then_str} || {else_str}"
    else:
        out = then_str or else_str

    return out, i


def extract_rows(text: str) -> List[Tuple[str, str, str, str, str]]:
    lines = text.splitlines()

    # Track the current heading stack by level
    # Map level -> Heading
    stack: Dict[int, Heading] = {}

    rows: List[Tuple[str, str, str, str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        # Update heading stack
        h = is_heading(line)
        if h:
            level = heading_level(h["num"])  # type: ignore[arg-type]
            # Prune deeper levels
            for k in list(stack.keys()):
                if k >= level:
                    stack.pop(k, None)
            stack[level] = h
            i += 1
            continue

        # Detect IF block
        if line.strip() == "IF":
            # Determine nearest subheading above with an ID (for 需求ID and 测试点)
            nearest_with_id: Optional[Heading] = None
            deepest_level = max(stack.keys()) if stack else None
            if deepest_level is not None:
                for lev in range(deepest_level, 0, -1):
                    head = stack.get(lev)
                    if head and head.get("id"):
                        nearest_with_id = head
                        break

            # Determine third-level heading for HIL初始条件
            third_level_heading = stack.get(3)

            # Parse conditions between IF and THEN
            cond_str, idx_at_then = parse_conditions(lines, i + 1)

            # Parse results under THEN/ELSE
            results_str, next_idx = parse_results(lines, idx_at_then)

            # Build fields
            req_id = nearest_with_id.get("id") if nearest_with_id else ""
            # 测试点: number + space + title without brackets and braces
            if nearest_with_id:
                test_point = f"{nearest_with_id['num']} {nearest_with_id['title']}"
            else:
                # fallback to deepest heading without ID
                if deepest_level is not None and stack.get(deepest_level):
                    h2 = stack[deepest_level]
                    test_point = f"{h2['num']} {h2['title']}"
                else:
                    test_point = ""

            # HIL初始条件: third-level title content without ID section
            if third_level_heading:
                hil_init = f"{third_level_heading['num']} {third_level_heading['title']}"
                # but the example wants only the text part, not the number? It shows only name. We'll keep only the text part.
                hil_init = third_level_heading['title']  # type: ignore[index]
            else:
                hil_init = ""

            # Clean fields per rules
            req_id = (req_id or "").strip()
            test_point = normalize_text(test_point)
            # Only keep number and title before any bracket in test_point; strip number? Example keeps number. Keep number + title
            # normalize_text already removed brackets and braces

            hil_init = normalize_text(hil_init)
            cond_str = normalize_text(cond_str)
            results_str = normalize_text(results_str)

            # Also, test_point should not include leading numbering? Example keeps number. So fine.
            # But they only want the heading title text (without number) for HIL初始条件 example. We already set hil_init to title only.

            # Append row: 需求ID, 测试点, HIL初始条件, HIL测试步骤, HIL预期结果
            rows.append((req_id, test_point, hil_init, cond_str, results_str))

            i = next_idx
            continue

        i += 1

    return rows


def write_csv(rows: List[Tuple[str, str, str, str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["需求ID", "测试点", "HIL初始条件", "HIL测试步骤", "HIL预期结果"])
        for r in rows:
            writer.writerow(list(r))


def main():
    if len(sys.argv) < 3:
        print("用法: python extract_requirements_table.py <输入txt路径> <输出csv路径>")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not in_path.exists():
        print(f"输入文件不存在: {in_path}")
        sys.exit(2)

    text = in_path.read_text(encoding="utf-8")
    rows = extract_rows(text)
    write_csv(rows, out_path)
    print(f"已生成: {out_path} ({len(rows)} 条)")


if __name__ == "__main__":
    main()