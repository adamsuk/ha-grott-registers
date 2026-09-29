"""Manual refresh. The scheduled poll is slow on purpose."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CLOCK_SOURCE, DOMAIN
from .coordinator import GrottCoordinator
from .entity import GrottEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [GrottRefreshButton(coordinator), GrottSyncClockButton(coordinator)]
    )


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


class GrottSyncClockButton(GrottEntity, ButtonEntity):
    """Write the grott server's local time into the datalogger."""

    _attr_icon = "mdi:clock-check"

    def __init__(self, coordinator: GrottCoordinator) -> None:
        super().__init__(coordinator, "sync_datalogger_time", "Sync datalogger time")

    @property
    def available(self) -> bool:
        return bool(self.coordinator.datalogger_id)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"sets_clock_from": CLOCK_SOURCE}

    async def async_press(self) -> None:
        await self.coordinator.async_sync_datalogger_time()
