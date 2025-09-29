#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import List, Tuple


WINDOW_ZERO_RANGE_RE = re.compile(
    r"\bwindow\s+0(?:\.0+)?(?:\s*(?:ms|s|us|ns))?\s*\.\.\s*([^\s]+)",
    flags=re.IGNORECASE,
)


def migrate_text(text: str) -> Tuple[str, int]:
    """Return (new_text, replacements_count)."""

    def _repl(m: re.Match[str]) -> str:
        end = m.group(1)
        return f"window {end}"

    new_text, n = WINDOW_ZERO_RANGE_RE.subn(_repl, text)
    return new_text, n


def process_file(path: Path, write: bool) -> int:
    original = path.read_text(encoding="utf-8")
    updated, count = migrate_text(original)
    if count > 0 and write:
        path.write_text(updated, encoding="utf-8")
    return count


def find_dsl_files(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.dsl") if p.is_file()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Migrate DSL 'window 0..X' to 'window X'")
    ap.add_argument("--root", default=str(Path.cwd()), help="Root directory to scan (default: CWD)")
    ap.add_argument("--write", action="store_true", help="Write changes back to files (default: dry-run)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    files = find_dsl_files(root)
    total_files = 0
    total_repls = 0

    for f in files:
        try:
            count = process_file(f, args.write)
        except Exception as e:
            print(f"ERROR processing {f}: {e}")
            continue
        if count > 0:
            total_files += 1
            total_repls += count
            action = "UPDATED" if args.write else "WOULD UPDATE"
            print(f"{action}: {f}  (+{count} change(s))")

    mode = "write" if args.write else "dry-run"
    print(f"Scan complete ({mode}). Files changed: {total_files}, replacements: {total_repls}.")


if __name__ == "__main__":
    main()

