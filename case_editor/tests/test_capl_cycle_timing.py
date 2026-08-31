"""周期报文调度：正常 8~11ms；偶发漏 tick 后不补 2~3ms 连发帧。"""
from __future__ import annotations

import tempfile
import unittest

from case_editor.src.capl_generation import (
    CAPL_MIN_GAP_TICKS_PER_MS,
    CAPL_TIMENOW_TICKS_PER_MS,
    capl_ms_to_timenow_ticks,
    is_cyclic_catchup_gap,
    next_cyclic_due_ticks,
    _build_can_file,
    parse_vsysvar,
)
from case_editor.tests.test_capl_mux_generation import MUX_VSYSVAR


def _intervals(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:])]


def _simulate_new_with_wakeups(wakeups_ms: list[int], cycle_ms: int = 10) -> list[int]:
    """按给定调度唤醒时刻跑新逻辑（到期才发，过近补发丢弃）。返回发送时刻 ms。"""
    period = capl_ms_to_timenow_ticks(cycle_ms)
    due = period
    last_tx = 0
    sent: list[int] = []
    for wake in wakeups_ms:
        now = capl_ms_to_timenow_ticks(wake)
        if due == 0 or now < due:
            continue
        if is_cyclic_catchup_gap(now, last_tx, period):
            due = next_cyclic_due_ticks(now, period)
            continue
        sent.append(wake)
        last_tx = now
        due = next_cyclic_due_ticks(now, period)
    return sent


class CaplCycleTimingMathTest(unittest.TestCase):
    def test_timenow_ticks_are_10us(self) -> None:
        self.assertEqual(capl_ms_to_timenow_ticks(10), 1000)
        self.assertEqual(CAPL_TIMENOW_TICKS_PER_MS, 100)
        self.assertEqual(CAPL_MIN_GAP_TICKS_PER_MS, 50)

    def test_normal_8_to_11ms_jitter_is_kept(self) -> None:
        """正常 Trace 间隔 8~11ms 应原样发送，不能当补发丢掉。"""
        period = capl_ms_to_timenow_ticks(10)
        last = capl_ms_to_timenow_ticks(10)
        for gap_ms in (8, 9, 10, 11):
            now = last + capl_ms_to_timenow_ticks(gap_ms)
            self.assertFalse(
                is_cyclic_catchup_gap(now, last, period),
                f"{gap_ms}ms 属于正常抖动",
            )

    def test_occasional_2_to_3ms_after_19ms_is_dropped(self) -> None:
        """偶发：10ms 格子漏到 19ms 后再在 21~22ms 补一帧，后一帧应丢弃。"""
        period = capl_ms_to_timenow_ticks(10)
        t0 = capl_ms_to_timenow_ticks(0)
        t19 = capl_ms_to_timenow_ticks(19)
        self.assertFalse(is_cyclic_catchup_gap(t19, t0, period))
        for follow_ms in (21, 22):
            follow = capl_ms_to_timenow_ticks(follow_ms)
            self.assertTrue(is_cyclic_catchup_gap(follow, t19, period))
            self.assertEqual(
                (next_cyclic_due_ticks(t19, period) - t19) / CAPL_TIMENOW_TICKS_PER_MS,
                10,
            )

    def test_late_tick_does_not_aim_at_original_20ms_slot(self) -> None:
        period = capl_ms_to_timenow_ticks(10)
        due = period
        late_now = capl_ms_to_timenow_ticks(19)
        next_due = next_cyclic_due_ticks(late_now, period)
        self.assertEqual((next_due - late_now) / CAPL_TIMENOW_TICKS_PER_MS, 10)
        catchup_due = due + period
        self.assertEqual((catchup_due - late_now) / CAPL_TIMENOW_TICKS_PER_MS, 1)
        self.assertNotEqual(next_due, catchup_due)

    def test_wakeup_stream_drops_only_the_catchup_frame(self) -> None:
        # 10ms 正常一帧后漏 tick，19ms 才发；21ms 的补发应丢掉，随后回到 10ms
        sent = _simulate_new_with_wakeups([10, 29, 31, 39, 49])
        self.assertEqual(sent, [10, 29, 39, 49])
        self.assertEqual(_intervals(sent), [19, 10, 10])


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
        self.assertIn("long last_tx_Media_0x32B;", content)
        self.assertNotIn("cancelTimer(", content)
        self.assertNotIn("setTimer(tmr_Media_0x32B", content)
        self.assertIn("due_Media_0x32B = _now + _ct * 100;", content)
        self.assertIn("_min = _ct * 50;", content)
        self.assertIn("if (_gap >= 0 && _gap < _min)", content)
        poll = content[content.index("void poll_Media_0x32B(long now)") :]
        poll = poll[: poll.index("\nvoid ")]
        self.assertIn("send_Media_0x32B();", poll)
        self.assertIn("last_tx_Media_0x32B = now;", poll)
        self.assertIn("  else\n    arm_Media_0x32B(now);", poll)
        sched = content[content.index("on timer tmr_sched") :]
        self.assertLess(sched.index("setTimer(tmr_sched, 1);"), sched.index("now = timeNow();"))
        self.assertLess(sched.index("now = timeNow();"), sched.index("poll_Media_0x32B(now);"))

    def test_begin_burst_clears_due_instead_of_cancel_timer(self) -> None:
        content = self._generate(MUX_VSYSVAR)
        begin = content[content.index("void begin_burst_Media_0x32B") :]
        begin = begin[: begin.index("\nvoid ")]
        self.assertIn("due_Media_0x32B = 0;", begin)
        self.assertIn("last_tx_Media_0x32B = timeNow();", begin)
        self.assertNotIn("cancelTimer", begin)
        self.assertIn("arm_Media_0x32B(timeNow());", begin)


if __name__ == "__main__":
    unittest.main()
