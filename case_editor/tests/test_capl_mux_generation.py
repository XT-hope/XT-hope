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
        self.assertIn("void output_all_Media_0x32B_groups()", content)
        self.assertIn("void apply_Media_0x32B_CSW_Enable_S()", content)
        self.assertIn("void sync_Media_0x32B_payload()", content)
        self.assertIn("fill_Media_0x32B_group(14);", content)
        self.assertIn("sync_Media_0x32B_payload();", content)
        self.assertIn("output_all_Media_0x32B_groups();", content)
        self.assertIn("output(msg_Media_0x32B);", content)
        self.assertIn("msg_Media_0x32B.CSW_Enable_S.phys = @media::Media_0x32B.CSW_Enable_S_Pv;", content)
        self.assertIn("if (msg_Media_0x32B.Child_ID_32B_S == 14)", content)
        self.assertIn("apply_Media_0x32B_CSW_Enable_S();", content)
        pv = content[content.index("on sysvar media::Media_0x32B.CSW_Enable_S_Pv") :]
        pv = pv[: pv.index("\n\n")]
        rv = content[content.index("on sysvar media::Media_0x32B.CSW_Enable_S_Rv") :]
        rv = rv[: rv.index("\n\n")]
        self.assertIn("apply_Media_0x32B_CSW_Enable_S();", pv)
        self.assertNotIn("apply_Media_0x32B_CSW_Enable_S();", rv)
        self.assertIn("msTimer tmr_Media_0x32B;", content)
        self.assertIn("void emit_Media_0x32B()", content)
        self.assertIn("on timer tmr_Media_0x32B", content)
        timer = content[content.index("on timer tmr_Media_0x32B") :]
        timer = timer[: timer.index("\n\n")]
        self.assertIn("emit_Media_0x32B();", timer)
        self.assertIn("fill_Media_0x32B_group(14);", timer)
        self.assertIn("sync_Media_0x32B_payload();", timer)
        self.assertLess(timer.index("emit_Media_0x32B();"), timer.index("fill_Media_0x32B_group(14);"))
        self.assertLess(timer.index("fill_Media_0x32B_group(14);"), timer.index("sync_Media_0x32B_payload();"))
        self.assertNotIn("send_Media_0x32B();", timer)
        self.assertNotIn("msTimer tmr_sched;", content)
        self.assertNotIn("timeNow()", content)
        self.assertNotIn("poll_emit_", content)
        self.assertNotIn("begin_burst_Media_0x32B", content)
        self.assertNotIn("burst_mux_Media_0x32B", content)
        self.assertNotIn("g_prev_Media_0x32B_", content)
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
            _build_send_function("Control", "Control", "Media", model.name, model, parsed, "", "")
        )
        self.assertIn("if (burst_mux_Media_0x32B >= 0)", send_body)
        self.assertIn("fill_Media_0x32B_group(burst_mux_Media_0x32B);", send_body)
        self.assertIn("sync_Media_0x32B_payload();", send_body)
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
            "      sync_Media_0x32B_payload();\n"
            "      output(msg_Media_0x32B);\n"
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
        self.assertIn("msTimer tmr_Media_0x32B;", content)
        self.assertNotIn("msTimer tmr_sched;", content)
        self.assertNotIn("due_Media_0x32B", content)
        self.assertNotIn("last_tx_Media_0x32B", content)
        self.assertNotIn("need_fill_Media_0x32B", content)
        self.assertNotIn("burst_mux_Media_0x32B", content)
        self.assertNotIn("g_prev_Media_0x32B_", content)
        self.assertNotIn("finish_burst_Media_0x32B", content)
        self.assertNotIn("begin_burst_Media_0x32B", content)
        self.assertIn("  arm_Media_0x32B();", content)
        self.assertIn("on timer tmr_Media_0x32B", content)
        self.assertIn("emit_Media_0x32B();", content)
        self.assertIn("fill_Media_0x32B_group(14);", content)
        self.assertNotIn("send_Media_0x32B();", content[content.index("on timer tmr_Media_0x32B") : content.index("void send_Media_0x32B")])
        self.assertIn("setTimer(tmr_Media_0x32B, _ct);", content)
        self.assertIn("  _ct = @media::Media_0x32B_Info.Media_0x32B_MsgCycleTime;", content)
        self.assertNotIn("timeNow()", content)
        self.assertNotIn("burst_left_Media_0x32B <= 0) return;", content)

    def test_sysvar_quiet_blocks_restore_and_linkage_retrigger(self) -> None:
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
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        inactive = "@media::Media_0x32B.CSW_Enable_S_inactive_value"
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_SigSendType != 0", content)
        self.assertIn("_old != _new", content)
        self.assertIn("@media::Media_0x32B.CSW_Enable_S_has_inactive_value == 1", content)
        self.assertIn(f"(_old == ({inactive}) && _new != ({inactive}))", content)
        self.assertIn(f"(_old != ({inactive}) && _new == ({inactive}))", content)
        self.assertNotIn(f"== {MSG_SEND_CA}", content)

    def test_ce_trigger_uses_send_additional_not_begin_burst(self) -> None:
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
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        self.assertIn("void send_additional_Media_0x32B(long mux_id)", content)
        self.assertNotIn("void begin_burst_Media_0x32B", content)
        self.assertNotIn("void finish_burst_Media_0x32B", content)
        self.assertIn("send_additional_Media_0x32B(14);", content)
        self.assertNotIn("begin_burst_Media_0x32B", content)
        self.assertNotIn("cancelTimer(tmr_Media_0x32B);", content[content.index("void send_additional_Media_0x32B") : content.index("void arm_Media_0x32B")])

        send_additional = content[
            content.index("void send_additional_Media_0x32B") : content.index("void arm_Media_0x32B")
        ]
        self.assertEqual(send_additional.count("fill_Media_0x32B_group(14);"), 2)
        self.assertEqual(send_additional.count("output(msg_Media_0x32B);"), 1)

    def test_ce_send_additional_increments_counter(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="3"',
            1,
        ).replace(
            '<structMember name="CSW_Enable_S_SigSendType" type="int" startValue="0"',
            '''<structMember name="Rolling_Cnt_S_Pv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Rolling_Cnt_S_Rv" type="int" startValue="0" minValue="0" maxValue="15" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Rolling_Cnt_S_Factor" type="float" startValue="1" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="Rolling_Cnt_S_Offset" type="float" startValue="0" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_SigSendType" type="int" startValue="0"''',
            1,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {
            "message_name": "Media_0x32B",
            "has_validation": True,
            "counter_signal": "Rolling_Cnt_S",
            "check_signal": "",
            "check_method": "crc16",
            "check_parameters": {},
        }
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

        send_additional = content[
            content.index("void send_additional_Media_0x32B") : content.index("void arm_Media_0x32B")
        ]
        fill_start = content.index("void fill_Media_0x32B_group")
        fill_group = content[fill_start : content.index("on sysvar media::Media_0x32B.CSW_Enable_S_Pv", fill_start)]
        self.assertIn("msg_Media_0x32B.Rolling_Cnt_S = cnt_Media_0x32B;", fill_group)
        self.assertEqual(send_additional.count("fill_Media_0x32B_group(14);"), 2)

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
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        self.assertTrue(model.get("CSW_Enable_S").has_inactive_value)
        self.assertTrue(model.get("CSW_Enable_S").has_inactive_flag_member)
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        content = _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})
        inactive = "@media::Media_0x32B.CSW_Enable_S_inactive_value"
        self.assertIn(f"(_old == ({inactive}) && _new != ({inactive}))", content)
        self.assertIn(f"(_old != ({inactive}) && _new == ({inactive}))", content)
        self.assertNotIn(f"== {MSG_SEND_IF_ACTIVE}", content)

    def test_apply_uses_phys_pv_not_in_fill(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR)
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        from case_editor.src.capl_generation import _build_all_apply_functions, _build_fill_group_function

        fill_content = "\n".join(
            _build_fill_group_function(
                "media", model.name, model, parsed, False, "", "", "crc16", {}
            )
        )
        apply_content = "\n".join(
            _build_all_apply_functions("media", model.name, model, "", "")
        )
        self.assertNotIn("CSW_Enable_S.phys", fill_content)
        self.assertIn("msg_Media_0x32B.CSW_Enable_S.phys = @media::Media_0x32B.CSW_Enable_S_Pv;", apply_content)
        self.assertIn("if (msg_Media_0x32B.Child_ID_32B_S == 14)", apply_content)

    def test_crc_uses_byte_array_for_checksum_lib(self) -> None:
        from case_editor.src.capl_generation import CHECKSUM_LIB, _build_refresh_crc_function

        self.assertIn("word PROJ_CRC16_CCITT(byte data[], long len", CHECKSUM_LIB)
        self.assertNotIn("message msg", CHECKSUM_LIB)

        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(MUX_VSYSVAR.replace(
                '<structMember name="CSW_Enable_S_SigSendType"',
                '''<structMember name="CRC_S_Pv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CRC_S_Rv" type="int" startValue="0" bitcount="32" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CRC_S_Factor" type="float" startValue="1" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CRC_S_Offset" type="float" startValue="0" bitcount="64" isSigned="false" encoding="65001" relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" comment=""/>
        <structMember name="CSW_Enable_S_SigSendType"''',
                1,
            ))
            path = fh.name

        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        lines = _build_refresh_crc_function(
            "media",
            model.name,
            model,
            parsed,
            True,
            "CRC_S",
            "crc16",
            {"poly": "0x1021", "init": "0xFFFF", "xorOut": "0x0000"},
        )
        content = "\n".join(lines)
        self.assertIn("void refresh_crc_Media_0x32B()", content)
        self.assertIn("PROJ_CRC16_CCITT(_data, _n, 0xFFFF, 0x1021, 0x0000);", content)
        self.assertIn("_data[", content)
        self.assertIn(".byte(_i)", content)

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

        from case_editor.src.capl_generation import _build_all_apply_functions

        lines = _build_all_apply_functions(
            "media", model.name, model, "", ""
        )
        content = "\n".join(lines)
        self.assertEqual(content.count("if (msg_Media_0x32B.Child_ID_32B_S == 14)"), 2)
        self.assertIn("CSW_Enable_S", content)
        self.assertIn("Other_S", content)

    def test_output_all_groups_fills_single_mux_id(self) -> None:
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
                groups=[14],
                initial_value="0",
            ),
        )
        content = "\n".join(_build_mux_output_all_groups_function("Msg_A", model))
        self.assertIn("void output_all_Msg_A_groups()", content)
        self.assertIn("fill_Msg_A_group(14);", content)
        self.assertIn("output(msg_Msg_A);", content)
        self.assertNotIn("for (i = 0;", content)
        self.assertNotIn("mux_ids", content)


if __name__ == "__main__":
    unittest.main()
