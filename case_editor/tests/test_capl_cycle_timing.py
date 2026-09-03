"""周期报文：独立 msTimer，到期先 emit(output) 再 fill。"""
from __future__ import annotations

import tempfile
import unittest

from case_editor.src.capl_generation import _build_can_file, parse_vsysvar
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR


class CaplCycleTimingGenerationTest(unittest.TestCase):
    def _generate(self, vsysvar: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        return _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

    def test_timer_emits_before_fill(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("void emit_Media_0x32B()", content)
        self.assertIn("output(msg_Media_0x32B);", content)
        self.assertNotIn("timeNow()", content)
        self.assertNotIn("tmr_sched", content)

        timer = content[content.index("on timer tmr_Media_0x32B") :]
        timer = timer[: timer.index("\n\n")]
        self.assertIn("emit_Media_0x32B();", timer)
        self.assertIn("fill_Media_0x32B_group(14);", timer)
        self.assertIn("arm_Media_0x32B();", timer)
        self.assertLess(timer.index("emit_Media_0x32B();"), timer.index("fill_Media_0x32B_group(14);"))
        self.assertLess(timer.index("fill_Media_0x32B_group(14);"), timer.index("arm_Media_0x32B();"))
        self.assertNotIn("send_Media_0x32B();", timer)

    def test_on_start_prepares_before_first_arm(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        start = content[content.index("on start") : content.index("void output_all_Media_0x32B_groups")]
        self.assertIn("sync_Media_0x32B_payload();", start)
        self.assertIn("fill_Media_0x32B_group(14);", start)
        self.assertLess(start.index("sync_Media_0x32B_payload();"), start.index("fill_Media_0x32B_group(14);"))
        self.assertLess(start.index("fill_Media_0x32B_group(14);"), start.index("arm_Media_0x32B();"))

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
        self.assertIn("fill_Media_0x32B_group(14);", handler)
        self.assertIn("sync_Media_0x32B_payload();", handler)
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


if __name__ == "__main__":
    unittest.main()
