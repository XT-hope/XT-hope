"""周期报文调度：避免 send 后再 setTimer 把 fill/output 耗时叠进周期。"""
from __future__ import annotations

import tempfile
import unittest

from case_editor.src.capl_generation import (
    CAPL_TIMENOW_TICKS_PER_MS,
    capl_ms_to_timenow_ticks,
    next_cyclic_due_ticks,
    _build_can_file,
    parse_vsysvar,
)
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR


def _old_output_times_ms(cycle_ms: int, send_ms: int, n: int) -> list[float]:
    """旧逻辑：on timer 里先 send，结束后再 setTimer(cycle)。output 记在 send 结束时刻。"""
    t = float(cycle_ms)
    outputs: list[float] = []
    for _ in range(n):
        outputs.append(t + send_ms)
        t = t + send_ms + cycle_ms
    return outputs


def _new_output_times_ms(cycle_ms: int, send_ms: int, n: int) -> list[float]:
    """新逻辑：下次到期 = 发送前 now + cycle，不追赶漏 tick。"""
    period = capl_ms_to_timenow_ticks(cycle_ms)
    now = 0
    due = period
    outputs: list[float] = []
    for _ in range(n):
        now = due
        outputs.append(now / CAPL_TIMENOW_TICKS_PER_MS + send_ms)
        due = next_cyclic_due_ticks(now, period)
    return outputs


def _intervals(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:])]


class CaplCycleTimingMathTest(unittest.TestCase):
    def test_timenow_ticks_are_10us(self) -> None:
        self.assertEqual(capl_ms_to_timenow_ticks(10), 1000)
        self.assertEqual(CAPL_TIMENOW_TICKS_PER_MS, 100)

    def test_old_set_timer_after_send_makes_19ms_interval(self) -> None:
        times = _old_output_times_ms(cycle_ms=10, send_ms=9, n=5)
        self.assertEqual(_intervals(times), [19, 19, 19, 19])

    def test_new_due_from_pre_send_now_keeps_10ms(self) -> None:
        times = _new_output_times_ms(cycle_ms=10, send_ms=9, n=5)
        self.assertEqual(_intervals(times), [10, 10, 10, 10])

    def test_late_tick_does_not_emit_catchup_2ms_frame(self) -> None:
        """调度晚到 19ms 时，下一帧应仍隔一个周期，而不是 20ms 格子上的补发。"""
        period = capl_ms_to_timenow_ticks(10)
        due = period
        late_now = capl_ms_to_timenow_ticks(19)
        self.assertGreaterEqual(late_now, due)
        next_due = next_cyclic_due_ticks(late_now, period)
        gap_ms = (next_due - late_now) / CAPL_TIMENOW_TICKS_PER_MS
        self.assertEqual(gap_ms, 10)
        catchup_due = due + period
        catchup_gap_ms = (catchup_due - late_now) / CAPL_TIMENOW_TICKS_PER_MS
        self.assertEqual(catchup_gap_ms, 1)
        self.assertNotEqual(next_due, catchup_due)


class CaplCycleTimingGenerationTest(unittest.TestCase):
    def _generate(self, vsysvar: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".vsysvar", delete=False, encoding="utf-8") as fh:
            fh.write(vsysvar)
            path = fh.name
        parsed = parse_vsysvar(path)
        model = parsed.messages["Media_0x32B"]
        msg_cfg = {"message_name": "Media_0x32B", "has_validation": False}
        return _build_can_file("media", "Media", 1, [(msg_cfg, model)], parsed, {model.name: 0x32B})

    def test_cyclic_uses_shared_scheduler_and_pre_send_now(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        self.assertIn("msTimer tmr_sched;", content)
        self.assertNotIn("cancelTimer(", content)
        self.assertNotIn("setTimer(tmr_Media_0x32B", content)
        self.assertIn("due_Media_0x32B = _now + _ct * 100;", content)
        poll = content[content.index("void poll_Media_0x32B(long now)") :]
        poll = poll[: poll.index("\nvoid ")]
        self.assertIn("send_Media_0x32B();", poll)
        self.assertIn("arm_Media_0x32B(now);", poll)
        self.assertIn(
            "  else\n    arm_Media_0x32B(now);",
            poll,
        )
        sched = content[content.index("on timer tmr_sched") :]
        self.assertLess(sched.index("setTimer(tmr_sched, 1);"), sched.index("now = timeNow();"))
        self.assertLess(sched.index("now = timeNow();"), sched.index("poll_Media_0x32B(now);"))

    def test_begin_burst_clears_due_instead_of_cancel_timer(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        begin = content[content.index("void begin_burst_Media_0x32B") :]
        begin = begin[: begin.index("\nvoid ")]
        self.assertIn("due_Media_0x32B = 0;", begin)
        self.assertNotIn("cancelTimer", begin)
        self.assertIn("arm_Media_0x32B(timeNow());", begin)


if __name__ == "__main__":
    unittest.main()
