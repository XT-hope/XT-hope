import argparse
import sys
from pathlib import Path

from .parser import parse_case_file, dump_case_json, ParserDefaults


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert Canoe DSL to JSON")
    parser.add_argument("input", help="Path to DSL file")
    parser.add_argument("-o", "--output", help="Path to write JSON (default: stdout)")
    parser.add_argument("--event-timeout-ms", type=int, default=ParserDefaults().default_event_timeout_ms,
                        help="Default timeout for after EventName when not specified (ms)")

    args = parser.parse_args(argv)

    defaults = ParserDefaults(default_event_timeout_ms=args.event_timeout_ms)
    result = parse_case_file(args.input, defaults=defaults)
    json_text = dump_case_json(result)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json_text, encoding="utf-8")
    else:
        sys.stdout.write(json_text + "\n")


if __name__ == "__main__":
    main()

