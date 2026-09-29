"""Entity descriptions for the registers that have a device-page control."""

from __future__ import annotations

from dataclasses import dataclass

from .codec import slot_registers


@dataclass(frozen=True)
class PercentRegister:
    """A 0-100 holding register written on its own."""

    address: int
    key: str
    name: str
    icon: str


@dataclass(frozen=True)
class SlotRegister:
    """One clock or enable register inside a three-register slot."""

    schedule: str
    slot: int
    which: str
    address: int
    key: str
    name: str
    extended: bool


PERCENT_REGISTERS = (
    PercentRegister(1090, "battery_charge_power", "Battery charge power", "mdi:battery-charging-80"),
    PercentRegister(1091, "battery_charge_stop", "Battery charge stop", "mdi:battery-high"),
    PercentRegister(1070, "grid_discharge_power", "Grid discharge power", "mdi:transmission-tower"),
    PercentRegister(1071, "grid_discharge_stop", "Grid discharge stop", "mdi:battery-arrow-down"),
)

AC_CHARGE = PercentRegister(1092, "ac_charge", "AC charge", "mdi:power-plug")

_WHICH_LABEL = {"start": "start", "end": "end", "enable": "enabled"}
_WHICH_ICON = {
    ("battery", "start"): "mdi:clock-start",
    ("battery", "end"): "mdi:clock-end",
    ("battery", "enable"): "mdi:battery-clock",
    ("grid", "start"): "mdi:clock-start",
    ("grid", "end"): "mdi:clock-end",
    ("grid", "enable"): "mdi:transmission-tower",
}


def slot_definitions(extended: bool) -> list[SlotRegister]:
    """Slots 1-3, plus 4-6 when the option is on."""
    last = 6 if extended else 3
    items: list[SlotRegister] = []
    for schedule, title in (("battery", "Battery first"), ("grid", "Grid first")):
        for slot in range(1, last + 1):
            start, stop, enable = slot_registers(schedule, slot)
            addresses = {"start": start, "end": stop, "enable": enable}
            for which, address in addresses.items():
                items.append(
                    SlotRegister(
                        schedule=schedule,
                        slot=slot,
                        which=which,
                        address=address,
                        key=f"{schedule}_slot_{slot}_{which}",
                        name=f"{title} {slot} {_WHICH_LABEL[which]}",
                        extended=slot > 3,
                    )
                )
    return items


def entity_unique_ids(inverter_id: str, extended: bool) -> set[str]:
    """Every unique id this config creates, used to drop stale entities."""
    keys = {
        f"{inverter_id}_priority",
        f"{inverter_id}_refresh",
        f"{inverter_id}_datalogger_time",
        f"{inverter_id}_sync_datalogger_time",
        f"{inverter_id}_battery_first_schedule",
        f"{inverter_id}_grid_first_schedule",
        f"{inverter_id}_load_first_schedule",
        f"{inverter_id}_{AC_CHARGE.key}",
    }
    keys.update(f"{inverter_id}_{item.key}" for item in PERCENT_REGISTERS)
    keys.update(f"{inverter_id}_{item.key}" for item in slot_definitions(extended))
    return keys
