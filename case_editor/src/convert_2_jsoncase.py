from pathlib import Path
from case_parser import parse_case_file, dump_case_json, ParserDefaults
from env_mapping import map_env_signal
from pathlib import Path
from typing import Tuple
import os
import json

# channel_conf_path = os.path.join(os.path.dirname(__file__), 'config_file', 'config.json')
# print(os.path.dirname(os.path.dirname(__file__)))

def convert_dsl_to_json(dsl_content: str,
                        # output_path: str | None = None,
                        event_timeout_ms: int = 500,
                        channel_conf_path: str = None) -> bool:
    """
    Parse DSL -> JSON, optionally map env signals, and write/print the result.
    Returns True on success, False on failure.
    """
    defaults = ParserDefaults(default_event_timeout_ms=event_timeout_ms)
    try:
        result = parse_case_file(dsl_content, defaults=defaults)
    except Exception as e:
        raise e

    # print(result)
    # Optional: map env signals defined in meta.signals.set
    try:
        signals = result.get("meta", {}).get("signals", {}).get("set", [])
        # print(signals)
        if signals:
            maped_signals = map_env_signal(signals, channel_conf_path=channel_conf_path)  # assumes available
            # 去重（可按需改为保持顺序）
            result["meta"]["signals"]["set"] = list(set(result["meta"]["signals"]["set"]))
            result["meta"]["signals"]["check"] = list(set(result["meta"]["signals"]["check"]))
            if maped_signals:
                for step in result.get("steps", []):
                    if step.get("type") == "set":
                        # 顶层 signal（可选存在）
                        sig = step.get("signal")
                        if sig:
                            parts = sig.split("::")
                            sig_type = parts[0] if parts else ""
                            sig_name = parts[-1] if len(parts) > 1 else ""
                            if sig_type.lower() == "env" and sig_name in maped_signals:
                                step["signal"] = maped_signals[sig_name]
                        # assignments
                        for assignment in step.get("assignments", []):
                            sig = assignment.get("signal", "")
                            parts = sig.split("::")
                            sig_type = parts[0] if parts else ""
                            sig_name = parts[-1] if len(parts) > 1 else ""
                            if sig_type.lower() == "env" and sig_name in maped_signals:
                                assignment["signal"] = maped_signals[sig_name]
    except Exception as e:
        raise e

    try:
        json_text = dump_case_json(result)
        # if output_path:
        #     Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        #     Path(output_path).write_text(json_text, encoding="utf-8")
        # else:
        #     print(json_text)
        return json_text
    except Exception as e:
        #print(f"Error writing output: {e}")
        raise e
    
if __name__== "__main__":
    convert_dsl_to_json("D:/Test/case_editor/projects/proj2/dsl_case/001.dsl", "D:/Test/case_editor/projects/proj2/json_case/tc_007.json", channel_conf_path=None)
