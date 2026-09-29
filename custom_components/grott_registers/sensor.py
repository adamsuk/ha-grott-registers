"""Read-only priority mode."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codec import priority_label
from .const import CLOCK_SOURCE, DATALOGGER_CLOCK_REGISTER, DOMAIN
from .coordinator import GrottCoordinator
from .entity import GrottEntity

PRIORITY_REGISTER = 1044


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [GrottPrioritySensor(coordinator), GrottDataloggerTimeSensor(coordinator)]
    )


class GrottPrioritySensor(GrottEntity, SensorEntity):
    """Register 1044. The inverter sets this from the active window."""

    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator: GrottCoordinator) -> None:
        super().__init__(coordinator, "priority", "Priority")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.raw(PRIORITY_REGISTER) is not None

    @property
    def native_value(self) -> str | None:
        raw = self.coordinator.raw(PRIORITY_REGISTER)
        if raw is None:
            return None
        return priority_label(raw)

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        return {"register": PRIORITY_REGISTER, "raw": self.coordinator.raw(PRIORITY_REGISTER)}


class GrottDataloggerTimeSensor(GrottEntity, SensorEntity):
    """Register 31. The schedule follows this clock."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: GrottCoordinator) -> None:
        super().__init__(coordinator, "datalogger_time", "Datalogger time")

    @property
    def available(self) -> bool:
        return self.coordinator.datalogger_time is not None

    @property
    def native_value(self) -> str | None:
        return self.coordinator.datalogger_time

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        return {
            "register": DATALOGGER_CLOCK_REGISTER,
            "set_from": CLOCK_SOURCE,
        }
