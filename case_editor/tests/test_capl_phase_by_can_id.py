"""capl_generation3：启动相位序号按 CAN ID 升序，不按列表顺序、不按周期。"""
from __future__ import annotations

import tempfile
import unittest
from typing import List, Tuple

from case_editor.src import capl_generation2 as gen2
from case_editor.src.capl_generation3 import (
    _build_can_file,
    _periodic_phase_indices,
    parse_vsysvar,
)
from case_editor.tests.test_capl_cycle_timing import _signal_members
from case_editor.tests.test_capl_startup_phase import (
    _func,
    _multi_cycle_vsysvar,
    _parse,
)


def _build_named(
    specs: List[Tuple[str, int]],
    frame_ids: dict,
    *,
    list_order: List[str] | None = None,
) -> str:
    parsed = _parse(_multi_cycle_vsysvar(specs))
    names = list_order if list_order is not None else [name for name, _cycle in specs]
    messages = [
        ({"message_name": name, "has_validation": False, "dlc": 8}, parsed.messages[name])
        for name in names
    ]
    return _build_can_file("demo", "ECU", 1, messages, parsed, frame_ids)


class CaplPhaseByCanIdTest(unittest.TestCase):
    def test_generation2_still_uses_list_order(self) -> None:
        specs = [("High_0x10C", 10), ("Low_0x100", 10), ("Mid_0x200", 20)]
        parsed = _parse(_multi_cycle_vsysvar(specs))
        names = ["High_0x10C", "Low_0x100", "Mid_0x200"]
        messages = [
            ({"message_name": n, "has_validation": False}, parsed.messages[n]) for n in names
        ]
        frame_ids = {"High_0x10C": 0x10C, "Low_0x100": 0x100, "Mid_0x200": 0x200}
        content = gen2._build_can_file("demo", "ECU", 1, messages, parsed, frame_ids)
        self.assertIn("_ph = 1 + (0 % _ct);", _func(content, "arm_start_High_0x10C"))
        self.assertIn("_ph = 1 + (1 % _ct);", _func(content, "arm_start_Low_0x100"))
        self.assertIn("_ph = 1 + (2 % _ct);", _func(content, "arm_start_Mid_0x200"))

    def test_indices_follow_can_id_not_list_order(self) -> None:
        specs = [("High_0x10C", 10), ("Low_0x100", 10), ("Mid_0x200", 20)]
        frame_ids = {"High_0x10C": 0x10C, "Low_0x100": 0x100, "Mid_0x200": 0x200}
        content = _build_named(specs, frame_ids, list_order=["High_0x10C", "Low_0x100", "Mid_0x200"])
        self.assertIn("_ph = 1 + (1 % _ct);", _func(content, "arm_start_High_0x10C"))
        self.assertIn("_ph = 1 + (0 % _ct);", _func(content, "arm_start_Low_0x100"))
        self.assertIn("_ph = 1 + (2 % _ct);", _func(content, "arm_start_Mid_0x200"))
        self.assertIn("capl_generation3", content)

    def test_missing_id_sorts_after_known_ids(self) -> None:
        specs = [("NoId", 10), ("HasId_0x050", 10)]
        parsed = _parse(_multi_cycle_vsysvar(specs))
        messages = [
            ({"message_name": "NoId", "has_validation": False}, parsed.messages["NoId"]),
            ({"message_name": "HasId_0x050", "has_validation": False}, parsed.messages["HasId_0x050"]),
        ]
        phases = _periodic_phase_indices(messages, 0, {"HasId_0x050": 0x50})
        self.assertEqual(phases["HasId_0x050"], 0)
        self.assertEqual(phases["NoId"], 1)

    def test_same_id_keeps_original_order_not_cycle(self) -> None:
        specs = [("SlowSame", 100), ("FastSame", 10)]
        parsed = _parse(_multi_cycle_vsysvar(specs))
        messages = [
            ({"message_name": "SlowSame", "has_validation": False}, parsed.messages["SlowSame"]),
            ({"message_name": "FastSame", "has_validation": False}, parsed.messages["FastSame"]),
        ]
        phases = _periodic_phase_indices(
            messages, 0, {"SlowSame": 0x100, "FastSame": 0x100}
        )
        self.assertEqual(phases["SlowSame"], 0)
        self.assertEqual(phases["FastSame"], 1)

    def test_event_does_not_take_an_index(self) -> None:
        vsysvar = f"""<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="demo" comment="" interface="">
{_cycle_xml("Event_0x010", 10, send_type=1)}{_cycle_xml("Cycle_0x200", 10, send_type=0)}    </namespace>
  </namespace>
</systemvariables>
"""
        parsed = _parse(vsysvar)
        messages = [
            ({"message_name": "Event_0x010", "has_validation": False}, parsed.messages["Event_0x010"]),
            ({"message_name": "Cycle_0x200", "has_validation": False}, parsed.messages["Cycle_0x200"]),
        ]
        phases = _periodic_phase_indices(
            messages, 0, {"Event_0x010": 0x10, "Cycle_0x200": 0x200}
        )
        self.assertNotIn("Event_0x010", phases)
        self.assertEqual(phases["Cycle_0x200"], 0)

    def test_smaller_id_on_later_node_gets_smaller_index(self) -> None:
        from case_editor.src.capl_generation3 import _periodic_phase_sort_key

        items = [
            (_periodic_phase_sort_key(0x10C, 0), "EPS", "EPS_0x10C"),
            (_periodic_phase_sort_key(0x100, 1), "IPB", "IPB_0x100"),
        ]
        items.sort(key=lambda row: row[0])
        self.assertEqual(items[0][2], "IPB_0x100")
        self.assertEqual(items[1][2], "EPS_0x10C")


def _cycle_xml(name: str, cycle_ms: int, send_type: int) -> str:
    from case_editor.tests.test_capl_startup_phase import _cycle_msg_xml

    return _cycle_msg_xml(name, cycle_ms, send_type)


if __name__ == "__main__":
    unittest.main()
