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


def parse_conditions(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    Parse conditions between IF and THEN.
    Returns (conditions_str, next_index_position_at_THEN_line)
    """
    aggregator: Optional[str] = None  # '&&' or '||'
    collected: List[str] = []

    i = start_idx
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if not line.strip():
            i += 1
            continue
        # Stop at THEN
        if line.strip().startswith("THEN"):
            break
        # Recognize guidance lines
        if "以下条件同时满足" in line:
            aggregator = "&&"
            i += 1
            continue
        if "以下条件满足其一" in line:
            aggregator = "||"
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
            # Split by standalone 'or'
            parts = split_conditions_by_or(item)
            if len(parts) > 1:
                collected.append(" || ".join(parts))
            else:
                collected.append(item)
        i += 1

    # Join collected conditions
    if not collected:
        cond_str = ""
    else:
        joiner = aggregator if aggregator else " && "
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
        out = f"THEN: {then_str} || ELSE: {else_str}"
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
            rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                         hil_init, cond_str, results_str))

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