"""capl_generation2：启动相位错开；热路径仍 emit → arm(周期) → fill。"""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from typing import List, Tuple

from case_editor.src.capl_generation2 import (
    _build_can_file,
    _periodic_phase_indices,
    parse_vsysvar,
)
from case_editor.src import capl_generation as gen1
from case_editor.tests.test_capl_cycle_timing import CYCLE_10MS_VSYSVAR, _signal_members
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR


def _func(content: str, name: str) -> str:
    marker = f"void {name}()"
    start = content.index(marker)
    end = content.index("\nvoid ", start + 1)
    return content[start:end]


def _on_start(content: str) -> str:
    start = content.index("on start")
    end = content.index("\nvoid ", start)
    return content[start:end]


def _on_timer(content: str, message_name: str) -> str:
    marker = f"on timer tmr_{message_name}"
    start = content.index(marker)
    rest = content[start:]
    end = rest.find("\n\n")
    return rest if end < 0 else rest[:end]


def _cycle_msg_xml(name: str, cycle_ms: int, send_type: int = 0) -> str:
    struct_info = name.lower() + "_info"
    struct_msg = name.lower()
    return f"""      <struct name="{struct_info}" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="{name}_MsgOn" type="int" startValue="1" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_MsgOff" type="int" startValue="0" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_MsgSendType" type="int" startValue="{send_type}" minValue="0" maxValue="4" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_MsgCycleTime" type="int" startValue="{cycle_ms}" minValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
      </struct>
      <variable name="{name}_Info" type="struct" structDefinition="demo::{struct_info}" bitcount="128" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
      <struct name="{struct_msg}" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="{name}_node" type="string" startValue="ECU" bitcount="0" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
{_signal_members("signalA")}      </struct>
      <variable name="{name}" type="struct" structDefinition="demo::{struct_msg}" bitcount="128" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
"""


def _multi_cycle_vsysvar(specs: List[Tuple[str, int]]) -> str:
    body = "".join(_cycle_msg_xml(name, cycle) for name, cycle in specs)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="demo" comment="" interface="">
{body}    </namespace>
  </namespace>
</systemvariables>
"""


def _parse(vsysvar: str):
    with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
        fh.write(vsysvar)
        path = fh.name
    return parse_vsysvar(path)


def _build_specs(specs: List[Tuple[str, int]], *, phase_index: int = 0, node: str = "ECU") -> str:
    parsed = _parse(_multi_cycle_vsysvar(specs))
    messages = []
    frame_ids = {}
    for i, (name, _cycle) in enumerate(specs):
        messages.append(({"message_name": name, "has_validation": False, "dlc": 8}, parsed.messages[name]))
        frame_ids[name] = 0x100 + i
    return _build_can_file("demo", node, 1, messages, parsed, frame_ids, phase_index=phase_index)


class CaplStartupPhaseTest(unittest.TestCase):
    def test_original_generator_unchanged_on_start_uses_arm(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(CYCLE_10MS_VSYSVAR)
            path = fh.name
        parsed = gen1.parse_vsysvar(path)
        model = parsed.messages["Cycle_0x100"]
        msg_cfg = {"message_name": "Cycle_0x100", "has_validation": False}
        content = gen1._build_can_file("demo", "ECU", 1, [(msg_cfg, model)], parsed, {model.name: 0x100})
        start = _on_start(content)
        self.assertIn("arm_Cycle_0x100();", start)
        self.assertNotIn("arm_start_Cycle_0x100();", start)
        self.assertNotIn("timeNow()", content)

    def test_plain_cycle_start_uses_arm_start_timer_uses_arm(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(CYCLE_10MS_VSYSVAR)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Cycle_0x100"]
        msg_cfg = {
            "message_name": "Cycle_0x100",
            "has_validation": True,
            "counter_signal": "msg_counter",
            "check_signal": "msg_crc",
            "check_method": "crc16",
            "check_parameters": {"poly": "0x1021", "init": "0xFFFF", "xorOut": "0x0000"},
            "dlc": 8,
        }
        content = _build_can_file("demo", "ECU", 1, [(msg_cfg, model)], parsed, {model.name: 0x100})
        start = _on_start(content)
        self.assertIn("fill_Cycle_0x100();", start)
        self.assertIn("arm_start_Cycle_0x100();", start)
        self.assertNotIn("\n    arm_Cycle_0x100();", start)
        self.assertLess(start.index("fill_Cycle_0x100();"), start.index("arm_start_Cycle_0x100();"))

        timer = _on_timer(content, "Cycle_0x100")
        self.assertIn("emit_Cycle_0x100();", timer)
        self.assertIn("arm_Cycle_0x100();", timer)
        self.assertNotIn("arm_start_Cycle_0x100();", timer)
        self.assertIn("fill_Cycle_0x100();", timer)
        self.assertLess(timer.index("emit_Cycle_0x100();"), timer.index("arm_Cycle_0x100();"))
        self.assertLess(timer.index("arm_Cycle_0x100();"), timer.index("fill_Cycle_0x100();"))

        arm = _func(content, "arm_Cycle_0x100")
        self.assertIn("setTimer(tmr_Cycle_0x100, _ct);", arm)

        arm_start = _func(content, "arm_start_Cycle_0x100")
        self.assertIn("_ph = 1 + (0 % _ct);", arm_start)
        self.assertIn("setTimer(tmr_Cycle_0x100, _ph);", arm_start)
        self.assertNotIn("timeNow()", content)
        self.assertIn("if (_ct <= 0)", arm_start)

        msg_on = content[content.index("on sysvar demo::Cycle_0x100_Info.Cycle_0x100_MsgOn") :]
        msg_on = msg_on[: msg_on.index("\n\n")]
        self.assertIn("arm_start_Cycle_0x100();", msg_on)
        self.assertNotIn("arm_Cycle_0x100();", msg_on)
        self.assertIn("cancelTimer(tmr_Cycle_0x100);", msg_on)
        self.assertIn(
            "on sysvar demo::Cycle_0x100_Info.Cycle_0x100_MsgOff",
            content,
        )

    def test_msg_off_and_timer_cancel_instead_of_return_only(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(CYCLE_10MS_VSYSVAR)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Cycle_0x100"]
        msg_cfg = {"message_name": "Cycle_0x100", "has_validation": False, "dlc": 8}
        content = _build_can_file("demo", "ECU", 1, [(msg_cfg, model)], parsed, {model.name: 0x100})

        allowed = (
            "@demo::Cycle_0x100_Info.Cycle_0x100_MsgOn == 1 && "
            "@demo::Cycle_0x100_Info.Cycle_0x100_MsgOff != 1"
        )
        start = _on_start(content)
        self.assertIn(f"if ({allowed})", start)
        self.assertIn("arm_start_Cycle_0x100();", start)

        timer = _on_timer(content, "Cycle_0x100")
        self.assertIn(f"if (!({allowed}))", timer)
        self.assertIn("cancelTimer(tmr_Cycle_0x100);", timer)
        self.assertIn("return;", timer)
        self.assertLess(timer.index("cancelTimer"), timer.index("emit_Cycle_0x100();"))
        self.assertLess(timer.index("emit_Cycle_0x100();"), timer.index("arm_Cycle_0x100();"))

        emit = content[content.index("void emit_Cycle_0x100()") :]
        emit = emit[: emit.index("\non timer")]
        self.assertIn("cancelTimer(tmr_Cycle_0x100);", emit)
        self.assertIn("return;", emit)
        self.assertNotIn("!= 1) return;", emit)
        self.assertNotIn("== 1) return;", emit)

        msg_off = content[content.index("on sysvar demo::Cycle_0x100_Info.Cycle_0x100_MsgOff") :]
        msg_off = msg_off[: msg_off.index("\n\n")]
        self.assertIn(f"if ({allowed})", msg_off)
        self.assertIn("cancelTimer(tmr_Cycle_0x100);", msg_off)
        self.assertIn("arm_start_Cycle_0x100();", msg_off)

    def test_send_additional_does_not_cancel_timer(self) -> None:
        vsysvar = CYCLE_10MS_VSYSVAR.replace(
            'Cycle_0x100_MsgSendType" type="int" startValue="0"',
            'Cycle_0x100_MsgSendType" type="int" startValue="3"',
            1,
        )
        parsed = _parse(vsysvar)
        model = parsed.messages["Cycle_0x100"]
        content = _build_can_file(
            "demo",
            "ECU",
            1,
            [({"message_name": "Cycle_0x100", "has_validation": False, "dlc": 8}, model)],
            parsed,
            {model.name: 0x100},
        )
        additional = content[content.index("void send_additional_Cycle_0x100") :]
        additional = additional[: additional.index("\nvoid arm_Cycle_0x100")]
        self.assertIn("if (!(", additional)
        self.assertIn(") return;", additional)
        self.assertNotIn("cancelTimer(tmr_Cycle_0x100);", additional)

    def test_ten_ms_messages_get_distinct_first_delays(self) -> None:
        specs = [(f"Cycle_0x{0x100 + i:X}", 10) for i in range(10)]
        specs.append(("Slow_0x200", 100))
        specs.append(("Slow_0x201", 100))
        content = _build_specs(specs)

        for i, (name, cycle) in enumerate(specs):
            arm_start = _func(content, f"arm_start_{name}")
            self.assertIn(f"_ph = 1 + ({i} % _ct);", arm_start)
            self.assertIn(f"setTimer(tmr_{name}, _ph);", arm_start)
            self.assertIn("if (_ct <= 0)", arm_start)
            start = _on_start(content)
            self.assertIn(f"arm_start_{name}();", start)
            timer = _on_timer(content, name)
            self.assertIn(f"arm_{name}();", timer)
            self.assertNotIn(f"arm_start_{name}();", timer)

        delays = [1 + (i % cycle) for i, (_name, cycle) in enumerate(specs)]
        self.assertEqual(delays[:10], list(range(1, 11)))
        self.assertEqual(delays[10], 11)
        self.assertEqual(delays[11], 12)
        self.assertTrue(all(d >= 1 for d in delays))
        self.assertEqual(len(set(delays)), 12)

        at_t100 = [name for i, (name, cycle) in enumerate(specs) if (1 + (i % cycle) - 100) % cycle == 0]
        self.assertEqual(at_t100, ["Cycle_0x109"])

    def test_phase_index_continues_across_nodes(self) -> None:
        specs_a = [("NodeA_0x10", 10), ("NodeA_0x11", 10)]
        specs_b = [("NodeB_0x20", 10), ("NodeB_0x21", 10)]
        parsed_a = _parse(_multi_cycle_vsysvar(specs_a))
        parsed_b = _parse(_multi_cycle_vsysvar(specs_b))
        messages_a = [({"message_name": n, "has_validation": False}, parsed_a.messages[n]) for n, _ in specs_a]
        content_a = _build_can_file("demo", "A", 1, messages_a, parsed_a, phase_index=0)
        messages_b = [({"message_name": n, "has_validation": False}, parsed_b.messages[n]) for n, _ in specs_b]
        content_b = _build_can_file(
            "demo",
            "B",
            1,
            messages_b,
            parsed_b,
            phase_index=len(_periodic_phase_indices(messages_a)),
        )
        self.assertIn("_ph = 1 + (0 % _ct);", _func(content_a, "arm_start_NodeA_0x10"))
        self.assertIn("_ph = 1 + (1 % _ct);", _func(content_a, "arm_start_NodeA_0x11"))
        self.assertIn("_ph = 1 + (2 % _ct);", _func(content_b, "arm_start_NodeB_0x20"))
        self.assertIn("_ph = 1 + (3 % _ct);", _func(content_b, "arm_start_NodeB_0x21"))

    def test_mux_on_start_uses_arm_start(self) -> None:
        parsed = _parse(MUX_VSYSVAR)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        start = _on_start(content)
        self.assertIn("arm_start_Media_0x32B();", start)
        self.assertNotIn("\n    arm_Media_0x32B();", start)
        timer = _on_timer(content, "Media_0x32B")
        self.assertIn("emit_Media_0x32B();", timer)
        self.assertIn("arm_Media_0x32B();", timer)
        self.assertNotIn("arm_start_Media_0x32B();", timer)
        self.assertNotIn("timeNow()", content)

    def test_event_only_has_no_arm_start(self) -> None:
        vsysvar = _multi_cycle_vsysvar([])
        vsysvar = f"""<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="demo" comment="" interface="">
{_cycle_msg_xml("Event_0x300", 10, send_type=1)}    </namespace>
  </namespace>
</systemvariables>
"""
        parsed = _parse(vsysvar)
        model = parsed.messages["Event_0x300"]
        content = _build_can_file(
            "demo",
            "ECU",
            1,
            [({"message_name": "Event_0x300", "has_validation": False}, model)],
            parsed,
            {model.name: 0x300},
        )
        self.assertNotIn("void arm_start_Event_0x300()", content)
        self.assertIn("void arm_Event_0x300()", content)

    def test_write_phase_stagger_artifact(self) -> None:
        specs = [(f"Cycle_0x{0x100 + i:X}", 10) for i in range(10)]
        specs += [("Slow_0x200", 100), ("Slow_0x201", 100)]
        content = _build_specs(specs)
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "demo_ECU_startup_phase.can")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        self.assertTrue(os.path.isfile(out_path))
        self.assertEqual(len(re.findall(r"void arm_start_", content)), 12)
        self.assertNotIn("timeNow()", content)


if __name__ == "__main__":
    unittest.main()
