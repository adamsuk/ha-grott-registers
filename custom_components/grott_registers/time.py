"""Start and end times for each battery-first and grid-first slot."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codec import decode_time
from .const import DOMAIN
from .coordinator import GrottCoordinator
from .definitions import SlotRegister, slot_definitions
from .entity import GrottEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrottSlotTime(coordinator, item)
        for item in slot_definitions(coordinator.extended)
        if item.which in ("start", "end")
    )


class GrottSlotTime(GrottEntity, TimeEntity):
    """One end of a slot. Changing it rewrites start, stop, and enable together."""

    def __init__(self, coordinator: GrottCoordinator, item: SlotRegister) -> None:
        super().__init__(coordinator, item.key, item.name)
        self._item = item
        self._attr_icon = "mdi:clock-start" if item.which == "start" else "mdi:clock-end"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.raw(self._item.address) is not None

    @property
    def native_value(self) -> dt_time | None:
        raw = self.coordinator.raw(self._item.address)
        if raw is None:
            return None
        try:
            hour, minute = decode_time(raw)
        except ValueError:
            return None
        return dt_time(hour, minute)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        return {"register": self._item.address, "raw": self.coordinator.raw(self._item.address)}

    async def async_set_value(self, value: dt_time) -> None:
        await self.coordinator.async_write_slot(
            self._item.schedule,
            self._item.slot,
            which=self._item.which,
            hour=value.hour,
            minute=value.minute,
        )
