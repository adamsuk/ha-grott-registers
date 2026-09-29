"""Pure helpers for grott register values.

Growatt packs a clock time into one 16-bit register: the high byte is the
hour and the low byte is the minute. 05:30 is 0x051e, not decimal 530.
"""

from __future__ import annotations

LOGGER_META_KEYS = frozenset({"ip", "port", "protocol"})

# start register of each (schedule, slot) triple. The next two registers are
# stop time and enable. ShinePhone shows slots 1-3. Slots 4-6 are present on
# some SPH firmware and are off unless the user opts in.
SLOT_START: dict[tuple[str, int], int] = {
    ("battery", 1): 1100,
    ("battery", 2): 1103,
    ("battery", 3): 1106,
    ("battery", 4): 1017,
    ("battery", 5): 1020,
    ("battery", 6): 1023,
    ("grid", 1): 1080,
    ("grid", 2): 1083,
    ("grid", 3): 1086,
    ("grid", 4): 1026,
    ("grid", 5): 1029,
    ("grid", 6): 1032,
}

SCHEDULE_ALIASES = {
    "battery": "battery",
    "battery_first": "battery",
    "grid": "grid",
    "grid_first": "grid",
}

PRIORITY_LABELS = {
    0: "Load first",
    1: "Battery first",
    2: "Grid first",
}

# Single-register writes to these addresses return OK and leave the slot unchanged.
SLOT_REGISTERS: frozenset[int] = frozenset(
    address
    for start in SLOT_START.values()
    for address in (start, start + 1, start + 2)
)


def normalize_schedule(name: str) -> str:
    """Return 'battery' or 'grid'."""
    try:
        return SCHEDULE_ALIASES[name.strip().lower()]
    except KeyError as err:
        raise ValueError(
            "schedule must be battery_first or grid_first"
        ) from err


def slot_registers(schedule: str, slot: int) -> tuple[int, int, int]:
    """Return (start, stop, enable) addresses for a schedule slot."""
    key = (normalize_schedule(schedule), slot)
    try:
        start = SLOT_START[key]
    except KeyError as err:
        raise ValueError("slot must be 1 to 6") from err
    return start, start + 1, start + 2


def poll_addresses(extended: bool) -> list[int]:
    """Registers read on each update.

    Priority, the charge/discharge limits, and slots 1-3. Slots 4-6 only when
    requested, because that block is not on every inverter.
    """
    addresses = [1044, 1070, 1071, 1090, 1091, 1092]
    last_slot = 6 if extended else 3
    for slot in range(1, last_slot + 1):
        for schedule in ("battery", "grid"):
            start, stop, enable = slot_registers(schedule, slot)
            addresses.extend((start, stop, enable))
    return addresses


def normalize_hex(value: str) -> str:
    """Return a 4-digit lower-case hex word."""
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not text:
        raise ValueError("empty register value")
    number = int(text, 16)
    if not 0 <= number <= 0xFFFF:
        raise ValueError("register value is outside 0-65535")
    return f"{number:04x}"


def decode_time(value: str) -> tuple[int, int]:
    """Decode a register word to (hour, minute)."""
    word = int(normalize_hex(value), 16)
    hour = (word >> 8) & 0xFF
    minute = word & 0xFF
    if hour > 23 or minute > 59:
        raise ValueError(f"register {value} is not a clock time")
    return hour, minute


def encode_time(hour: int, minute: int) -> str:
    """Encode hour and minute as a 4-digit hex word."""
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time must be within 00:00-23:59")
    return f"{hour:02x}{minute:02x}"


def parse_clock(value: str) -> tuple[int, int]:
    """Parse 'HH:MM' or 'HH:MM:SS'."""
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError("time must look like 05:30")
    return decode_time(encode_time(int(parts[0]), int(parts[1])))


def format_clock(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def encode_enable(enabled: bool) -> str:
    return "0001" if enabled else "0000"


def decode_enable(value: str) -> bool | None:
    """Return True, False, or None when the word is not an on/off flag."""
    word = int(normalize_hex(value), 16)
    if word == 1:
        return True
    if word == 0:
        return False
    return None


def decode_percent(value: str) -> int:
    word = int(normalize_hex(value), 16)
    if not 0 <= word <= 100:
        raise ValueError(f"register {value} is not a 0-100 percent")
    return word


def pack_slot(start: str, stop: str, enable: str) -> str:
    """Concatenated hex for one multiregister write."""
    packed = normalize_hex(start) + normalize_hex(stop) + normalize_hex(enable)
    if len(packed) != 12:
        raise ValueError("a slot value must be three 16-bit words")
    return packed


def inverters_from_payload(payload: dict) -> dict[str, str]:
    """Map inverter serial to datalogger serial from GET /inverter."""
    found: dict[str, str] = {}
    if not isinstance(payload, dict):
        return found
    for datalogger_id, info in payload.items():
        if not isinstance(info, dict):
            continue
        for key, value in info.items():
            if key in LOGGER_META_KEYS or not isinstance(value, dict):
                continue
            found[str(key)] = str(datalogger_id)
    return found


def priority_label(value: str) -> str:
    try:
        word = int(normalize_hex(value), 16)
    except ValueError:
        return value
    return PRIORITY_LABELS.get(word, f"Unknown ({word})")
