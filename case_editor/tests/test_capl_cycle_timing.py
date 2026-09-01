"""周期报文：每条报文独立 msTimer，到期 send 后重新 arm。"""
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

    def test_per_message_timer_send_then_arm(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("msTimer tmr_Media_0x32B;", content)
        self.assertNotIn("msTimer tmr_sched;", content)
        self.assertNotIn("timeNow()", content)
        self.assertNotIn("poll_emit_", content)
        self.assertNotIn("poll_prepare_", content)
        self.assertNotIn("due_Media_0x32B", content)
        self.assertNotIn("last_tx_Media_0x32B", content)
        self.assertNotIn("need_fill_Media_0x32B", content)

        timer = content[content.index("on timer tmr_Media_0x32B") :]
        timer = timer[: timer.index("\n\n")]
        self.assertIn("send_Media_0x32B();", timer)
        self.assertIn("arm_Media_0x32B();", timer)
        self.assertLess(timer.index("send_Media_0x32B();"), timer.index("arm_Media_0x32B();"))

    def test_arm_uses_set_timer_with_cycle_time(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        arm = content[content.index("void arm_Media_0x32B") :]
        arm = arm[: arm.index("\nvoid ")]
        self.assertIn("setTimer(tmr_Media_0x32B, _ct);", arm)
        self.assertIn("@media::Media_0x32B_Info.Media_0x32B_MsgCycleTime", arm)

    def test_begin_burst_cancels_timer_and_uses_arm(self) -> None:
        vsysvar = MUX_VSYSVAR.replace(
            'Media_0x32B_MsgSendType" type="int" startValue="0"',
            'Media_0x32B_MsgSendType" type="int" startValue="1"',
            1,
        )
        content = self._generate(vsysvar)
        begin = content[content.index("void begin_burst_Media_0x32B") :]
        begin = begin[: begin.index("\nvoid ")]
        self.assertIn("cancelTimer(tmr_Media_0x32B);", begin)
        self.assertIn("send_Media_0x32B();", begin)
        self.assertIn("arm_Media_0x32B();", begin)
        self.assertNotIn("timeNow()", begin)


if __name__ == "__main__":
    unittest.main()
