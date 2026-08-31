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


def _write_vsysvar(text: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        return fh.name


class CaplMuxGenerationTest(unittest.TestCase):
    def test_parse_mux_metadata(self) -> None:
        parsed = parse_vsysvar(_write_vsysvar(MUX_VSYSVAR))
        model = parsed.messages["Media_0x32B"]
        self.assertIsNotNone(model.mux)
        self.assertEqual(model.mux.mux_signal_name, "Child_ID_32B_S")
        self.assertEqual(model.mux.groups, [14])
        self.assertEqual(model.mux.initial_value, "0")
        self.assertEqual(model.info.msg_send_type, 0)
        self.assertEqual(model.info.msg_cycle_time_ms, 100)

    def test_cycle_mux_uses_cyclic_timer_without_burst(self) -> None:
        parsed = parse_vsysvar(_write_vsysvar(MUX_VSYSVAR))
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("fill_Media_0x32B_group(long mux_id)", content)
        self.assertIn("void output_all_Media_0x32B_groups()", content)
        self.assertIn("output_all_Media_0x32B_groups();", content)
        self.assertIn("setTimer(tmr_Media_0x32B, 100);", content)
        self.assertIn(
            "on timer tmr_Media_0x32B\n"
            "{\n"
            "  arm_Media_0x32B();\n"
            "  send_Media_0x32B();\n"
            "}",
            content,
        )
        self.assertNotIn("setTimerCyclic", content)
        self.assertNotIn("begin_burst_Media_0x32B", content)
        self.assertNotIn("finish_burst_Media_0x32B", content)
        self.assertNotIn("burst_left_Media_0x32B", content)
        self.assertNotIn("Media_0x32B_MsgSendType", content)
        self.assertNotIn("g_prev_Media_0x32B_", content)

    def test_ce_mux_generates_burst_and_periodic_timer(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="3"',
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
        </structMember>''',
            1,
        )
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("begin_burst_Media_0x32B", content)
        self.assertIn("finish_burst_Media_0x32B", content)
        self.assertIn("burst_left_Media_0x32B > 0", content)
        self.assertNotIn("Media_0x32B_MsgSendType", content)
        self.assertIn("if (_old != _new)", content)
        self.assertIn("begin_burst_Media_0x32B(_use_fast);", content)

    def test_event_burst_send_uses_burst_mux_not_dead_code(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        from case_editor.src.capl_generation import _build_send_function

        send_body = "\n".join(
            _build_send_function("Control", "Control", "Media", model.name, model, parsed)
        )
        self.assertIn("if (burst_mux_Media_0x32B >= 0)", send_body)
        self.assertIn("fill_Media_0x32B_group(burst_mux_Media_0x32B);", send_body)
        self.assertNotIn("Media_0x32B_MsgSendType", send_body)

    def test_burst_block_does_not_fallthrough_to_periodic_send(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        from case_editor.src.capl_generation import _build_send_function

        send_body = "\n".join(
            _build_send_function("Control", "Control", "Media", model.name, model, parsed)
        )
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

    def test_sysvar_quiet_blocks_restore_and_linkage_retrigger(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="3"',
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
        </structMember>''',
            1,
        )
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("long g_sv_quiet_Media_0x32B;", content)
        self.assertIn("if (g_sv_quiet_Media_0x32B != 0)", content)
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_Rv = _newRv;", content)
        finish_idx = content.index("void finish_burst_Media_0x32B()")
        restore_block = content[finish_idx : finish_idx + 800]
        shadow_idx = restore_block.index("g_prev_Media_0x32B_CSW_Enable_S_Pv")
        sv_idx = restore_block.index("@media::Media_0x32B.CSW_Enable_S_Pv =")
        self.assertLess(shadow_idx, sv_idx)

    def test_ca_trigger_uses_both_inactive_edges(self) -> None:
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
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        inactive = "@media::Media_0x32B.CSW_Enable_S_inactive_value"
        self.assertNotIn("Media_0x32B_MsgSendType", content)
        self.assertIn("_old != _new", content)
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_has_inactive_value == 1", content)
        self.assertIn(f"(_old == ({inactive}) && _new != ({inactive}))", content)
        self.assertIn(f"(_old != ({inactive}) && _new == ({inactive}))", content)
        self.assertIn("begin_burst_Media_0x32B(_use_fast);", content)

    def test_if_active_triggers_on_both_inactive_edges(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="2"',
            1,
        ).replace(
            'CSW_Enable_S_has_inactive_value" type="int" startValue="0"',
            'CSW_Enable_S_has_inactive_value" type="int" startValue="1"',
            1,
        ).replace(
            '<structMember name="CSW_Enable_S_use_inactive_value"',
            '''<structMember name="CSW_Enable_S_inactive_value" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_use_inactive_value"''',
            1,
        )
        parsed = parse_vsysvar(_write_vsysvar(vsysvar))
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        inactive = "@media::Media_0x32B.CSW_Enable_S_inactive_value"
        self.assertNotIn("Media_0x32B_MsgSendType", content)
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_has_inactive_value == 1", content)
        self.assertIn(f"(_old == ({inactive}) && _new != ({inactive}))", content)
        self.assertIn(f"(_old != ({inactive}) && _new == ({inactive}))", content)

    def test_fill_group_merges_same_mux_id(self) -> None:
        parsed = parse_vsysvar(_write_vsysvar(MUX_VSYSVAR))
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

    def test_output_all_groups_uses_nonconst_array_for_multiple_ids(self) -> None:
        from case_editor.src.capl_generation import (
            MessageModel,
            MuxMetadata,
            _build_mux_output_all_groups_function,
        )

        mux_signal = SignalModel(name="Mux_S", is_multiplexer=True)
        model = MessageModel(
            name="Msg_A",
            mux=MuxMetadata(
                mux_signal_name="Mux_S",
                mux_signal=mux_signal,
                groups=[1, 14, 3, 12, 13],
                initial_value="0",
            ),
        )
        content = "\n".join(_build_mux_output_all_groups_function("Msg_A", model))
        self.assertIn("void output_all_Msg_A_groups()", content)
        self.assertIn("long mux_ids[] = {1, 14, 3, 12, 13};", content)
        self.assertNotIn("const long", content)
        self.assertIn("for (i = 0; i < 5; i++)", content)
        self.assertIn("fill_Msg_A_group(mux_ids[i]);", content)
        self.assertIn("output(msg_Msg_A);", content)
        self.assertNotIn("fill_Msg_A_group(1);", content)


if __name__ == "__main__":
    unittest.main()
