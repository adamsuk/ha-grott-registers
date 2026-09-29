"""Codec tests. These do not need Home Assistant."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

# Load the pure modules without executing the integration package, which
# imports Home Assistant at import time.
_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "grott_registers"
_pkg = types.ModuleType("grott_registers")
_pkg.__path__ = [str(_ROOT)]
_pkg.__package__ = "grott_registers"
sys.modules["grott_registers"] = _pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"grott_registers.{name}", _ROOT / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_codec = _load("codec")
_definitions = _load("definitions")

SLOT_REGISTERS = _codec.SLOT_REGISTERS
decode_enable = _codec.decode_enable
decode_percent = _codec.decode_percent
decode_time = _codec.decode_time
encode_time = _codec.encode_time
format_clock = _codec.format_clock
inverters_from_payload = _codec.inverters_from_payload
normalize_datalogger_time = _codec.normalize_datalogger_time
normalize_schedule = _codec.normalize_schedule
pack_slot = _codec.pack_slot
parse_clock = _codec.parse_clock
poll_addresses = _codec.poll_addresses
priority_label = _codec.priority_label
schedule_blocks = _codec.schedule_blocks
slot_registers = _codec.slot_registers
entity_unique_ids = _definitions.entity_unique_ids
slot_definitions = _definitions.slot_definitions


class CodecTest(unittest.TestCase):
    def test_clock_round_trip(self) -> None:
        self.assertEqual(encode_time(0, 0), "0000")
        self.assertEqual(encode_time(5, 30), "051e")
        self.assertEqual(encode_time(10, 55), "0a37")
        self.assertEqual(encode_time(10, 58), "0a3a")
        self.assertEqual(encode_time(23, 15), "170f")
        self.assertEqual(encode_time(23, 59), "173b")
        self.assertEqual(decode_time("051e"), (5, 30))
        self.assertEqual(format_clock(*decode_time("170f")), "23:15")

    def test_parse_clock_ignores_seconds(self) -> None:
        self.assertEqual(parse_clock("05:30:00"), (5, 30))

    def test_pack_live_slot(self) -> None:
        self.assertEqual(pack_slot("0000", "051e", "0001"), "0000051e0001")

    def test_enable_and_percent(self) -> None:
        self.assertTrue(decode_enable("0001"))
        self.assertFalse(decode_enable("0000"))
        self.assertIsNone(decode_enable("1737"))
        self.assertEqual(decode_percent("0064"), 100)
        self.assertEqual(decode_percent("000a"), 10)

    def test_priority(self) -> None:
        self.assertEqual(priority_label("0000"), "Load first")
        self.assertEqual(priority_label("0001"), "Battery first")
        self.assertEqual(priority_label("0002"), "Grid first")

    def test_slot_map(self) -> None:
        self.assertEqual(slot_registers("battery_first", 1), (1100, 1101, 1102))
        self.assertEqual(slot_registers("grid_first", 1), (1080, 1081, 1082))
        self.assertEqual(slot_registers("battery", 4), (1017, 1018, 1019))
        self.assertEqual(slot_registers("grid", 4), (1026, 1027, 1028))
        self.assertIn(1100, SLOT_REGISTERS)
        self.assertNotIn(1092, SLOT_REGISTERS)
        self.assertEqual(normalize_schedule("Grid_First"), "grid")

    def test_poll_list(self) -> None:
        basic = poll_addresses(False)
        extended = poll_addresses(True)
        self.assertEqual(len(basic), 24)
        self.assertEqual(len(extended), 42)
        self.assertIn(1101, basic)
        self.assertNotIn(1017, basic)
        self.assertIn(1028, extended)

    def test_inverter_payload(self) -> None:
        payload = {
            "KWK1CJC15P": {
                "ip": "127.0.0.1",
                "port": 48630,
                "protocol": "06",
                "KTM0CM8032": {"inverterno": "51", "power": 0},
            }
        }
        self.assertEqual(inverters_from_payload(payload), {"KTM0CM8032": "KWK1CJC15P"})

    def test_entity_ids_cover_slots(self) -> None:
        basic = slot_definitions(False)
        self.assertEqual(len(basic), 18)
        ids = entity_unique_ids("KTM0CM8032", False)
        self.assertIn("KTM0CM8032_battery_slot_1_end", ids)
        self.assertNotIn("KTM0CM8032_battery_slot_4_start", ids)
        extended = entity_unique_ids("KTM0CM8032", True)
        self.assertIn("KTM0CM8032_grid_slot_4_enable", extended)
        self.assertIn("KTM0CM8032_datalogger_time", ids)
        self.assertIn("KTM0CM8032_sync_datalogger_time", ids)
        self.assertIn("KTM0CM8032_battery_first_schedule", ids)
        self.assertIn("KTM0CM8032_grid_first_schedule", ids)
        self.assertIn("KTM0CM8032_load_first_schedule", ids)
        self.assertGreater(len(extended), len(ids))

    def test_datalogger_clock_text(self) -> None:
        self.assertEqual(
            normalize_datalogger_time("  2026-09-29 11:24:00\x00"),
            "2026-09-29 11:24:00",
        )
        with self.assertRaises(ValueError):
            normalize_datalogger_time(" \x00 ")

    def test_schedule_uses_enabled_windows_and_load_first_gaps(self) -> None:
        registers = {
            1100: "0000",
            1101: "051e",
            1102: "0001",
            1103: "0a37",
            1104: "0a3a",
            1105: "0000",
            1106: "0000",
            1107: "0000",
            1108: "0000",
            1080: "170f",
            1081: "173b",
            1082: "0000",
            1083: "0000",
            1084: "0000",
            1085: "0000",
            1086: "0000",
            1087: "0000",
            1088: "0000",
        }
        blocks = schedule_blocks(registers, False)
        self.assertEqual(
            [(block.mode, block.start_minute, block.end_minute, block.slot) for block in blocks],
            [("battery", 0, 5 * 60 + 30, 1), ("load", 5 * 60 + 30, 24 * 60, None)],
        )

    def test_schedule_splits_midnight_and_ignores_odd_enable(self) -> None:
        registers = {
            1100: "1600",
            1101: "0200",
            1102: "0001",
            1080: "0100",
            1081: "0300",
            1082: "0001",
            1026: "0000",
            1027: "1727",
            1028: "1737",
        }
        blocks = schedule_blocks(registers, True)
        shown = [(block.mode, block.start_minute, block.end_minute, block.slot) for block in blocks]
        self.assertEqual(
            shown,
            [
                ("battery", 0, 2 * 60, 1),
                ("grid", 60, 3 * 60, 1),
                ("load", 3 * 60, 22 * 60, None),
                ("battery", 22 * 60, 24 * 60, 1),
            ],
        )


if __name__ == "__main__":
    unittest.main()
