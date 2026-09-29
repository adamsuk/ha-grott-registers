"""Manual refresh. The scheduled poll is slow on purpose."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrottCoordinator
from .entity import GrottEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GrottRefreshButton(coordinator)])


class GrottRefreshButton(GrottEntity, ButtonEntity):
    """Read the schedule registers now."""

    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: GrottCoordinator) -> None:
        super().__init__(coordinator, "refresh", "Refresh registers")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
        if not self.coordinator.last_update_success:
            message = self.coordinator.last_exception
            raise HomeAssistantError(
                f"Refresh failed: {message}" if message else "Refresh failed"
            )
