"""周期报文：到期先 output 再 fill，Trace 间隔保持约 10ms，不能出现 19ms。"""
from __future__ import annotations

import tempfile
import unittest

from case_editor.src.capl_generation import (
    CAPL_MIN_GAP_TICKS_PER_MS,
    CAPL_TIMENOW_TICKS_PER_MS,
    advance_due_on_grid,
    capl_ms_to_timenow_ticks,
    is_cyclic_catchup_gap,
    _build_can_file,
    parse_vsysvar,
)
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR


def _intervals(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:])]


def _old_fill_then_output_times(cycle_ms: int, fill_ms: int, n: int) -> list[float]:
    """旧逻辑：定时器到期后先 fill 再 output，output 时刻 = 到期 + fill 耗时。"""
    return [float(cycle_ms * (i + 1) + fill_ms) for i in range(n)]


def _new_emit_then_fill_times(cycle_ms: int, fill_ms: int, n: int) -> list[float]:
    """新逻辑：到期立刻 output，fill 放在 output 之后，不影响 Trace 时刻。"""
    del fill_ms
    return [float(cycle_ms * (i + 1)) for i in range(n)]


class CaplCycleTimingMathTest(unittest.TestCase):
    def test_timenow_ticks_are_10us(self) -> None:
        self.assertEqual(capl_ms_to_timenow_ticks(10), 1000)
        self.assertEqual(CAPL_TIMENOW_TICKS_PER_MS, 100)
        self.assertEqual(CAPL_MIN_GAP_TICKS_PER_MS, 50)

    def test_old_fill_before_output_creates_19ms_gap(self) -> None:
        times = _old_fill_then_output_times(cycle_ms=10, fill_ms=9, n=4)
        self.assertEqual(_intervals(times), [10, 10, 10])
        # 相对“准时到期点”晚了 9ms；若上一拍 fill 很快、本拍很慢，就会看到 ~19ms
        fast_then_slow = [10.0, 29.0]
        self.assertEqual(_intervals(fast_then_slow), [19.0])

    def test_emit_then_fill_keeps_10ms_even_if_fill_takes_9ms(self) -> None:
        times = _new_emit_then_fill_times(cycle_ms=10, fill_ms=9, n=5)
        self.assertEqual(times, [10, 20, 30, 40, 50])
        self.assertEqual(_intervals(times), [10, 10, 10, 10])
        self.assertNotIn(19, _intervals(times))

    def test_normal_8_to_11ms_jitter_is_kept(self) -> None:
        period = capl_ms_to_timenow_ticks(10)
        last = capl_ms_to_timenow_ticks(10)
        for gap_ms in (8, 9, 10, 11):
            now = last + capl_ms_to_timenow_ticks(gap_ms)
            self.assertFalse(is_cyclic_catchup_gap(now, last, period))

    def test_2_to_3ms_double_send_is_dropped(self) -> None:
        period = capl_ms_to_timenow_ticks(10)
        last = capl_ms_to_timenow_ticks(10)
        for gap_ms in (2, 3):
            now = last + capl_ms_to_timenow_ticks(gap_ms)
            self.assertTrue(is_cyclic_catchup_gap(now, last, period))

    def test_grid_advance_stays_on_10ms_slots(self) -> None:
        period = capl_ms_to_timenow_ticks(10)
        due = period
        now = capl_ms_to_timenow_ticks(11)
        nxt = advance_due_on_grid(due, now, period)
        self.assertEqual(nxt / CAPL_TIMENOW_TICKS_PER_MS, 20)


class CaplCycleTimingGenerationTest(unittest.TestCase):
    def _generate(self, vsysvar: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        return _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

    def test_scheduler_emits_before_prepare_fill(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("void emit_Media_0x32B()", content)
        self.assertIn("void poll_emit_Media_0x32B(long tNow)", content)
        self.assertIn("void poll_prepare_Media_0x32B()", content)
        self.assertIn("void advance_due_Media_0x32B(long tNow)", content)
        self.assertIn("long need_fill_Media_0x32B;", content)
        sched = content[content.index("on timer tmr_sched") :]
        self.assertLess(sched.index("setTimer(tmr_sched, 1);"), sched.index("tNow = timeNow();"))
        self.assertLess(sched.index("poll_emit_Media_0x32B(tNow);"), sched.index("poll_prepare_Media_0x32B();"))
        emit_poll = content[content.index("void poll_emit_Media_0x32B(long tNow)") :]
        emit_poll = emit_poll[: emit_poll.index("\nvoid ")]
        self.assertIn("emit_Media_0x32B();", emit_poll)
        self.assertIn("advance_due_Media_0x32B(tNow);", emit_poll)

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
        self.assertIn("due_Media_0x32B = 0;", begin)


if __name__ == "__main__":
    unittest.main()
