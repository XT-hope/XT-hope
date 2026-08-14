import tempfile
import unittest
from pathlib import Path

from case_editor.src.capl_generation import (
    MSG_SEND_CA,
    MSG_SEND_CE,
    MSG_SEND_EVENT,
    MSG_SEND_IF_ACTIVE,
    SignalModel,
    _build_can_file,
    parse_vsysvar,
)


MUX_VSYSVAR = """<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="media" comment="" interface="">
      <struct name="media_0x32b_info" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="Media_0x32B_MsgOn" type="int" startValue="1" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Media_0x32B_MsgOff" type="int" startValue="0" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Media_0x32B_MsgSendType" type="int" startValue="0" minValue="0" maxValue="4" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Media_0x32B_MsgCycleTime" type="int" startValue="100" minValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Media_0x32B_is_multiplexed" type="int" startValue="1" minValue="0" maxValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
      </struct>
      <variable name="Media_0x32B_Info" type="struct" structDefinition="media::media_0x32b_info" bitcount="160" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
      <struct name="media_0x32b" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember name="Media_0x32B_node" type="string" startValue="Media" bitcount="0" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_Pv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_Rv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_Factor" type="float" startValue="1" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_Offset" type="float" startValue="0" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_has_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_use_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_has_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_use_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_SigSendType" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Child_ID_32B_S_is_multiplexer" type="int" startValue="1" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_Pv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_Rv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_Factor" type="float" startValue="1" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_Offset" type="float" startValue="0" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_has_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_use_special_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_has_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_use_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_SigSendType" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_is_multiplexer" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_multiplexer_id" type="int" startValue="14" minValue="0" maxValue="255" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
      </struct>
      <variable name="Media_0x32B" type="struct" structDefinition="media::media_0x32b" bitcount="640" isSigned="true" encoding="65001" anlyzLocal="2" readOnly="false" valueSequence="false" unit="" comment=""/>
    </namespace>
  </namespace>
</systemvariables>
"""


class CaplMuxGenerationTest(unittest.TestCase):
    def test_parse_mux_metadata(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        self.assertIsNotNone(model.mux)
        self.assertEqual(model.mux.mux_signal_name, "Child_ID_32B_S")
        self.assertEqual(model.mux.groups, [14])
        self.assertEqual(model.mux.initial_value, "0")

    def test_generated_capl_contains_mux_loop_and_burst(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("fill_Media_0x32B_group(long mux_id)", content)
        self.assertNotIn("g_mux_groups_", content)
        self.assertNotIn("const long", content)
        self.assertIn("fill_Media_0x32B_group(14);", content)
        self.assertIn("output(msg_Media_0x32B);", content)
        self.assertIn("if (mux_id == 14)", content)
        self.assertIn(f"== {MSG_SEND_EVENT}", content)
        self.assertIn(f"== {MSG_SEND_IF_ACTIVE}", content)
        self.assertIn("burst_mux_Media_0x32B = 14;", content)
        self.assertIn(f"== {MSG_SEND_CE}", content)
        self.assertIn(f"== {MSG_SEND_CA}", content)
        self.assertIn("burst_left_Media_0x32B > 0", content)
        self.assertNotIn("g_prev_Media_0x32B_Child_ID_32B_S_Pv", content)
        self.assertNotIn("@media::Media_0x32B.Child_ID_32B_S_Pv = 0;", content)

    def test_event_burst_send_uses_burst_mux_not_dead_code(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        from case_editor.src.capl_generation import _build_send_function

        send_body = "\n".join(
            _build_send_function("Control", "Control", "Media", model.name, model, parsed)
        )
        self.assertIn("if (burst_mux_Media_0x32B >= 0)", send_body)
        self.assertIn("fill_Media_0x32B_group(burst_mux_Media_0x32B);", send_body)
        self.assertNotIn(
            "    return;\n  }\n  if (burst_left_Media_0x32B > 0 && burst_mux_Media_0x32B >= 0)",
            send_body,
        )

    def test_burst_block_does_not_fallthrough_to_periodic_send(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        from case_editor.src.capl_generation import _build_send_function

        send_body = "\n".join(
            _build_send_function("Control", "Control", "Media", model.name, model, parsed)
        )
        # burst_left 块末尾必须有 return，防止 Event burst 误落到周期全 group 发送
        self.assertIn(
            "    if (burst_mux_Media_0x32B >= 0)\n"
            "    {\n"
            "      fill_Media_0x32B_group(burst_mux_Media_0x32B);\n"
            "      output(msg_Media_0x32B);\n"
            "      return;\n"
            "    }\n"
            "    return;\n"
            "  }",
            send_body,
        )

    def test_core_burst_vars_declared_without_msg_send_type(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            '<structMember name="Media_0x32B_MsgSendType" type="int" startValue="0" minValue="0" maxValue="4" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>\n',
            "",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("long burst_left_Media_0x32B;", content)
        self.assertIn("long burst_fast_Media_0x32B;", content)
        self.assertNotIn("burst_mux_Media_0x32B", content)
        self.assertNotIn("g_prev_Media_0x32B_", content)
        self.assertNotIn("finish_burst_Media_0x32B", content)
        self.assertNotIn("begin_burst_Media_0x32B", content)
        # 无 MsgSendType：按 Cycle 启动周期定时器，timer 只 send+arm
        self.assertIn("  arm_Media_0x32B();", content)
        self.assertIn(
            "on timer tmr_Media_0x32B\n{\n  send_Media_0x32B();\n  arm_Media_0x32B();\n}",
            content,
        )
        self.assertIn("  _ct = @media::Media_0x32B_Info.Media_0x32B_MsgCycleTime;", content)
        self.assertNotIn("burst_left_Media_0x32B <= 0) return;", content)

    def test_sysvar_quiet_blocks_restore_and_linkage_retrigger(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("long g_sv_quiet_Media_0x32B;", content)
        self.assertIn("if (g_sv_quiet_Media_0x32B != 0)", content)
        self.assertIn("g_sv_quiet_Media_0x32B = g_sv_quiet_Media_0x32B + 1;", content)
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_Rv = _newRv;", content)
        finish_idx = content.index("void finish_burst_Media_0x32B()")
        restore_block = content[finish_idx : finish_idx + 800]
        shadow_idx = restore_block.index("g_prev_Media_0x32B_CSW_Enable_S_Pv")
        sv_idx = restore_block.index("@media::Media_0x32B.CSW_Enable_S_Pv =")
        self.assertLess(shadow_idx, sv_idx)
        self.assertIn("g_sv_quiet_Media_0x32B = g_sv_quiet_Media_0x32B + 1;", restore_block)

    def test_ca_trigger_requires_non_cycle_and_not_inactive(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="4"',
            1,
        ).replace(
            '<structMember name="CSW_Enable_S_SigSendType" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>',
            '''<structMember name="CSW_Enable_S_SigSendType" type="int" startValue="2" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment="">
          <valuetable name="CSW_Enable_S_SigSendTypeVt">
            <valuetableentry value="0" description="Cycle"/>
            <valuetableentry value="1" description="OnWrite"/>
            <valuetableentry value="2" description="OnChange"/>
            <valuetableentry value="3" description="Event"/>
          </valuetable>
        </structMember>
        <structMember name="CSW_Enable_S_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>''',
            1,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        self.assertIn("== 4 && @media::Media_0x32B.CSW_Enable_S_SigSendType != 0", content)
        self.assertIn("_old != _new", content)
        self.assertIn("_new != (@media::Media_0x32B.CSW_Enable_S_inactive_value)", content)

    def test_fill_group_merges_same_mux_id(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        clone = SignalModel(
            name="Other_S",
            has_pv=True,
            has_multiplexer_id=True,
            multiplexer_id=14,
        )
        model.signals.append(clone)
        model.signal_index["Other_S"] = clone

        from case_editor.src.capl_generation import _build_fill_group_function

        lines = _build_fill_group_function(
            "media", model.name, model, parsed, False, "", "", "crc16", {}
        )
        content = "\n".join(lines)
        self.assertEqual(content.count("if (mux_id == 14)"), 1)
        self.assertIn("CSW_Enable_S", content)
        self.assertIn("Other_S", content)


if __name__ == "__main__":
    unittest.main()
