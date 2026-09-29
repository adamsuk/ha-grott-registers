"""Percent limits: charge rate, charge stop, discharge rate, discharge stop."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codec import normalize_hex
from .const import DOMAIN
from .coordinator import GrottCoordinator
from .definitions import PERCENT_REGISTERS, PercentRegister
from .entity import GrottEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(GrottPercentNumber(coordinator, spec) for spec in PERCENT_REGISTERS)


class GrottPercentNumber(GrottEntity, NumberEntity):
    """A 0-100 register. These are not part of a time slot, so a single write sticks."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: GrottCoordinator, spec: PercentRegister) -> None:
        super().__init__(coordinator, spec.key, spec.name)
        self._address = spec.address
        self._attr_icon = spec.icon

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.raw(self._address) is not None

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.raw(self._address)
        if raw is None:
            return None
        try:
            return float(int(normalize_hex(raw), 16))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        return {"register": self._address, "raw": self.coordinator.raw(self._address)}

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_percent(self._address, int(value))
