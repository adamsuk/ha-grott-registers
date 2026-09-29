"""Grott register browser and schedule editor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .codec import encode_time, normalize_schedule, parse_clock
from .const import (
    CLOCK_SOURCE,
    CONF_EXTENDED,
    CONF_INVERTER,
    DOMAIN,
    PLATFORMS,
    SERVICE_READ,
    SERVICE_REFRESH,
    SERVICE_SYNC_CLOCK,
    SERVICE_WRITE,
    SERVICE_WRITE_MULTI,
    SERVICE_WRITE_SLOT,
)
from .coordinator import GrottCoordinator
from .definitions import entity_unique_ids

_READ_SCHEMA = vol.Schema(
    {
        vol.Required("register"): vol.All(int, vol.Range(min=0, max=4095)),
        vol.Optional("target", default="inverter"): vol.In(["inverter", "datalogger"]),
        vol.Optional("format"): vol.In(["hex", "dec", "text"]),
        vol.Optional("inverter_id"): str,
    }
)
_WRITE_SCHEMA = _READ_SCHEMA.extend(
    {vol.Required("value"): str, vol.Optional("format", default="dec"): vol.In(["hex", "dec", "text"])}
)
_SLOT_SCHEMA = vol.Schema(
    {
        vol.Required("schedule"): str,
        vol.Required("slot"): vol.All(int, vol.Range(min=1, max=6)),
        vol.Required("start"): str,
        vol.Required("end"): str,
        vol.Required("enabled"): bool,
        vol.Optional("inverter_id"): str,
    }
)
_MULTI_SCHEMA = vol.Schema(
    {
        vol.Required("start_register"): vol.All(int, vol.Range(min=0, max=4095)),
        vol.Required("end_register"): vol.All(int, vol.Range(min=0, max=4095)),
        vol.Required("value"): str,
        vol.Optional("inverter_id"): str,
    }
)
_REFRESH_SCHEMA = vol.Schema({vol.Optional("inverter_id"): str})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GrottCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _drop_stale_entities(hass, entry)
    _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), "grott_registers_initial_poll"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_READ,
                SERVICE_WRITE,
                SERVICE_WRITE_SLOT,
                SERVICE_WRITE_MULTI,
                SERVICE_REFRESH,
                SERVICE_SYNC_CLOCK,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _drop_stale_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities from a previous options choice, such as slots 4-6."""
    registry = er.async_get(hass)
    valid = entity_unique_ids(
        entry.data[CONF_INVERTER], bool(entry.options.get(CONF_EXTENDED, False))
    )
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id not in valid:
            registry.async_remove(entity.entity_id)


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_READ):
        return

    async def _read(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        target = call.data.get("target", "inverter")
        fmt = call.data.get("format") or ("text" if target == "datalogger" else "hex")
        return await coordinator.async_read_any(target, call.data["register"], fmt)

    async def _write(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        return await coordinator.async_write_any(
            call.data.get("target", "inverter"),
            call.data["register"],
            str(call.data["value"]),
            call.data.get("format", "dec"),
        )

    async def _write_slot(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        try:
            schedule = normalize_schedule(call.data["schedule"])
            start_hour, start_minute = parse_clock(call.data["start"])
            end_hour, end_minute = parse_clock(call.data["end"])
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_write_slot(
            schedule,
            call.data["slot"],
            start=encode_time(start_hour, start_minute),
            stop=encode_time(end_hour, end_minute),
            enabled=bool(call.data["enabled"]),
        )
        return {"updated": True, "schedule": schedule, "slot": call.data["slot"]}

    async def _write_multi(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        start = call.data["start_register"]
        end = call.data["end_register"]
        if end < start:
            raise HomeAssistantError("end_register is before start_register")
        value = str(call.data["value"]).strip().lower().removeprefix("0x")
        expected_len = (end - start + 1) * 4
        if len(value) != expected_len or any(char not in "0123456789abcdef" for char in value):
            raise HomeAssistantError(
                f"value must be {expected_len} hex characters, one 16-bit word per register"
            )
        readback = await coordinator.async_write_raw_multi(start, end, value)
        return {"registers": readback}

    async def _refresh(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise HomeAssistantError(f"Refresh failed: {coordinator.last_exception}")
        return {"registers": len(coordinator.data or {})}

    async def _sync_clock(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_from_call(hass, call)
        value = await coordinator.async_sync_datalogger_time()
        return {"datalogger_time": value, "set_from": CLOCK_SOURCE}

    hass.services.async_register(
        DOMAIN, SERVICE_READ, _read, schema=_READ_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE, _write, schema=_WRITE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_WRITE_SLOT,
        _write_slot,
        schema=_SLOT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_WRITE_MULTI,
        _write_multi,
        schema=_MULTI_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _refresh,
        schema=_REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_CLOCK,
        _sync_clock,
        schema=_REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _coordinator_from_call(hass: HomeAssistant, call: ServiceCall) -> GrottCoordinator:
    entries: dict[str, GrottCoordinator] = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("Grott Registers is not configured")
    wanted = call.data.get("inverter_id")
    if wanted:
        for coordinator in entries.values():
            if coordinator.inverter_id == wanted:
                return coordinator
        raise HomeAssistantError(f"No Grott entry for inverter {wanted}")
    if len(entries) == 1:
        return next(iter(entries.values()))
    serials = ", ".join(sorted(item.inverter_id for item in entries.values()))
    raise HomeAssistantError(f"Pass inverter_id. Configured inverters: {serials}")
