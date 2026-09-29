"""Diagnostics dump of the registers last read from the inverter."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_INVERTER, CONF_PORT, DOMAIN
from .coordinator import GrottCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: GrottCoordinator = hass.data[DOMAIN][entry.entry_id]
    registers = {
        str(address): value for address, value in sorted((coordinator.data or {}).items())
    }
    return {
        "host": entry.data[CONF_HOST],
        "port": entry.data[CONF_PORT],
        "inverter_id": entry.data[CONF_INVERTER],
        "last_update_success": coordinator.last_update_success,
        "registers": registers,
    }
