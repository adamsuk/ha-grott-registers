"""AC charge, and the enable flag of each schedule slot."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codec import decode_enable
from .const import DOMAIN
from .coordinator import GrottCoordinator
from .definitions import AC_CHARGE, SlotRegister, slot_definitions
from .entity import GrottEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [GrottAcChargeSwitch(coordinator)]
    entities.extend(
        GrottSlotSwitch(coordinator, item)
        for item in slot_definitions(coordinator.extended)
        if item.which == "enable"
    )
    async_add_entities(entities)


class GrottAcChargeSwitch(GrottEntity, SwitchEntity):
    """Register 1092. Allows the grid to charge the battery during battery first."""

    _attr_icon = AC_CHARGE.icon

    def __init__(self, coordinator: GrottCoordinator) -> None:
        super().__init__(coordinator, AC_CHARGE.key, AC_CHARGE.name)
        self._address = AC_CHARGE.address

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.raw(self._address) is not None

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.raw(self._address)
        if raw is None:
            return None
        return decode_enable(raw)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        return {"register": self._address, "raw": self.coordinator.raw(self._address)}

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_switch(self._address, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_switch(self._address, False)


class GrottSlotSwitch(GrottEntity, SwitchEntity):
    """Enable flag. Written together with that slot's start and stop times."""

    def __init__(self, coordinator: GrottCoordinator, item: SlotRegister) -> None:
        super().__init__(coordinator, item.key, item.name)
        self._item = item
        self._attr_icon = "mdi:battery-clock" if item.schedule == "battery" else "mdi:transmission-tower"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.raw(self._item.address) is not None

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.raw(self._item.address)
        if raw is None:
            return None
        return decode_enable(raw)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        return {"register": self._item.address, "raw": self.coordinator.raw(self._item.address)}

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_slot(
            self._item.schedule, self._item.slot, enabled=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_slot(
            self._item.schedule, self._item.slot, enabled=False
        )
