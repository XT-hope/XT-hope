"""周期报文：独立 msTimer；Mux 报文走 mux_idx 轮询。"""
from __future__ import annotations

import os
import tempfile
import unittest

from typing import Optional

from case_editor.src.capl_generation import _build_can_file, parse_vsysvar
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR

MUX_FILL = "fill_Media_0x32B_group(mux_ids_Media_0x32B[mux_idx_Media_0x32B]);"


def _signal_members(name: str, *, mux: bool = False, mux_id: Optional[int] = None) -> str:
    extra = ""
    if mux:
        extra += (
            f'        <structMember name="{name}_is_multiplexer" type="int" startValue="1" '
            'minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" '
            'relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>\n'
        )
    elif mux_id is not None:
        extra += (
            f'        <structMember name="{name}_is_multiplexer" type="int" startValue="0" '
            'minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" '
            'relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>\n'
            f'        <structMember name="{name}_multiplexer_id" type="int" startValue="{mux_id}" '
            'minValue="0" maxValue="255" bitcount="32" isSigned="false" encoding="65001" '
            'relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>\n'
        )
    return f"""        <structMember name="{name}_Pv" type="int" startValue="0" minValue="0" maxValue="255" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_Rv" type="int" startValue="0" minValue="0" maxValue="255" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_Factor" type="float" startValue="1" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_Offset" type="float" startValue="0" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_has_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_use_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_has_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_use_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="{name}_SigSendType" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
{extra}"""


CYCLE_10MS_VSYSVAR = f"""<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="demo" comment="" interface="">
      <struct name="cycle_0x100_info" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="Cycle_0x100_MsgOn" type="int" startValue="1" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Cycle_0x100_MsgOff" type="int" startValue="0" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Cycle_0x100_MsgSendType" type="int" startValue="0" minValue="0" maxValue="4" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Cycle_0x100_MsgCycleTime" type="int" startValue="10" minValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Cycle_0x100_WrongCRCFlag" type="int" startValue="0" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Cycle_0x100_WrongCounterFlag" type="int" startValue="0" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
      </struct>
      <variable name="Cycle_0x100_Info" type="struct" structDefinition="demo::cycle_0x100_info" bitcount="192" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
      <struct name="cycle_0x100" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="Cycle_0x100_node" type="string" startValue="ECU" bitcount="0" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
{_signal_members("signalA")}{_signal_members("signalB")}{_signal_members("signalC")}{_signal_members("signalD")}{_signal_members("msg_counter")}{_signal_members("msg_crc")}      </struct>
      <variable name="Cycle_0x100" type="struct" structDefinition="demo::cycle_0x100" bitcount="640" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
    </namespace>
  </namespace>
</systemvariables>
"""


class CaplCycleTimingGenerationTest(unittest.TestCase):
    def _generate(self, vsysvar: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        return _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

    def test_mux_timer_round_robin(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("long mux_ids_Media_0x32B[1] = {14};", content)
        self.assertNotIn("timeNow()", content)
        self.assertNotIn("tmr_sched", content)

        timer = content[content.index("on timer tmr_Media_0x32B") :]
        timer = timer[: timer.index("\n\n")]
        self.assertIn(MUX_FILL, timer)
        self.assertIn("emit_Media_0x32B();", timer)
        self.assertIn("if (mux_idx_Media_0x32B >= 1)", timer)
        self.assertIn("arm_Media_0x32B();", timer)
        self.assertLess(timer.index("emit_Media_0x32B();"), timer.index("arm_Media_0x32B();"))
        self.assertLess(timer.index("arm_Media_0x32B();"), timer.index(MUX_FILL))
        self.assertNotIn("send_Media_0x32B();", timer)

    def test_on_start_prepares_before_first_arm(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        start = content[content.index("on start") : content.index("void output_all_Media_0x32B_groups")]
        self.assertIn("mux_idx_Media_0x32B = 0;", start)
        self.assertIn(MUX_FILL, start)
        self.assertLess(start.index(MUX_FILL), start.index("arm_Media_0x32B();"))

    def test_begin_burst_still_uses_send(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        content = self._generate(vsysvar)
        begin = content[content.index("void begin_burst_Media_0x32B") :]
        begin = begin[: begin.index("\nvoid ")]
        self.assertIn("send_Media_0x32B();", begin)

    def test_msg_on_controls_timer(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("on sysvar media::Media_0x32B_Info.Media_0x32B_MsgOn", content)
        handler = content[
            content.index("on sysvar media::Media_0x32B_Info.Media_0x32B_MsgOn") :
        ]
        handler = handler[: handler.index("\n\n")]
        self.assertIn("@media::Media_0x32B_Info.Media_0x32B_MsgOn == 1", handler)
        self.assertIn(MUX_FILL, handler)
        self.assertNotIn("sync_Media_0x32B_payload();", handler)
        self.assertIn("arm_Media_0x32B();", handler)
        self.assertIn("cancelTimer(tmr_Media_0x32B);", handler)

    def test_on_start_arms_only_when_msg_on(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgOn" type="int" startValue="1"',
            'Media_0x32B_MsgOn" type="int" startValue="0"',
            1,
        )
        content = self._generate(vsysvar)
        start = content[content.index("on start") : content.index("void output_all_Media_0x32B_groups")]
        self.assertIn("if (@media::Media_0x32B_Info.Media_0x32B_MsgOn == 1)", start)
        self.assertIn("    arm_Media_0x32B();", start)
        self.assertNotIn("\n  arm_Media_0x32B();", start)

    def test_plain_cycle_emits_then_arms_then_fills(self) -> None:
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
        content = _build_can_file(
            "demo", "ECU", 1, [(msg_cfg, model)], parsed, {model.name: 0x100}
        )
        timer = content[content.index("on timer tmr_Cycle_0x100") :]
        timer = timer[: timer.index("\n\n")]
        self.assertIn("emit_Cycle_0x100();", timer)
        self.assertIn("arm_Cycle_0x100();", timer)
        self.assertIn("fill_Cycle_0x100();", timer)
        self.assertLess(timer.index("emit_Cycle_0x100();"), timer.index("arm_Cycle_0x100();"))
        self.assertLess(timer.index("arm_Cycle_0x100();"), timer.index("fill_Cycle_0x100();"))
        self.assertIn("PROJ_CRC16_CCITT", content)
        self.assertIn("msg_Cycle_0x100.signalA.phys = @demo::Cycle_0x100.signalA_Pv;", content)
        start = content[content.index("on start") :]
        start = start[: start.index("\n\n")]
        self.assertLess(start.index("fill_Cycle_0x100();"), start.index("arm_Cycle_0x100();"))

    def test_generate_cycle_10ms_node_capl_artifact(self) -> None:
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
        content = _build_can_file(
            "demo", "ECU", 1, [(msg_cfg, model)], parsed, {model.name: 0x100}
        )
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "demo_ECU_Cycle_0x100.can")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        self.assertTrue(os.path.isfile(out_path))
        self.assertIn("on timer tmr_Cycle_0x100", content)
        self.assertIn("void fill_Cycle_0x100()", content)


if __name__ == "__main__":
    unittest.main()
