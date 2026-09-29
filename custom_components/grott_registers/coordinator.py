"""Polling and verified writes for one inverter."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrottApiError, GrottClient
from .codec import (
    SLOT_REGISTERS,
    decode_enable,
    encode_enable,
    encode_time,
    normalize_hex,
    pack_slot,
    poll_addresses,
    slot_registers,
)
from .const import (
    CONF_DATALOGGER,
    CONF_EXTENDED,
    CONF_HOST,
    CONF_INVERTER,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)


class GrottCoordinator(DataUpdateCoordinator[dict[int, str]]):
    """Reads the schedule registers and writes them back through grottserver.

    A time slot is three registers. Growatt ignores a write to just one of
    them, so start, stop, and enable always go out together. The HTTP call
    often returns OK even when the inverter kept the old value, so every
    write is checked with a fresh read.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = GrottClient(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
        )
        self.inverter_id: str = entry.data[CONF_INVERTER]
        self.datalogger_id: str = entry.data.get(CONF_DATALOGGER) or ""
        scan_minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Grott {self.inverter_id}",
            update_interval=timedelta(minutes=scan_minutes),
        )
        # Held for a whole poll and for every write. The coordinator assigns
        # self.data after this lock is released, so polls update that dict in
        # place and writes mutate the same object. A fresh dict here would let
        # a stale poll replace a write that landed in between.
        self._write_lock = asyncio.Lock()

    @property
    def extended(self) -> bool:
        return bool(self.entry.options.get(CONF_EXTENDED, False))

    @property
    def device_info(self) -> DeviceInfo:
        host = self.entry.data[CONF_HOST]
        port = self.entry.data[CONF_PORT]
        return DeviceInfo(
            identifiers={(DOMAIN, self.inverter_id)},
            name=f"Growatt {self.inverter_id}",
            manufacturer="Growatt",
            model="Grott registers",
            sw_version=VERSION,
            configuration_url=f"http://{host}:{port}/",
        )

    def raw(self, address: int) -> str | None:
        if not self.data:
            return None
        value = self.data.get(address)
        return None if value is None else str(value)

    async def _async_update_data(self) -> dict[int, str]:
        addresses = poll_addresses(self.extended)
        async with self._write_lock:
            # Copy so a slow poll keeps the previous snapshot visible. Publish
            # into the existing dict at the end so a write in the release gap
            # mutates the same object the coordinator is about to assign.
            current: dict[int, str] = dict(self.data or {})
            failures = 0
            for address in addresses:
                try:
                    current[address] = await self.client.async_read_register(
                        target="inverter",
                        device_id=self.inverter_id,
                        register=address,
                    )
                except GrottApiError as err:
                    failures += 1
                    _LOGGER.warning("Register %s was not read: %s", address, err)
            if failures == len(addresses):
                raise UpdateFailed("grottserver returned no register values")
            if self.data is None:
                self.data = current
            else:
                self.data.clear()
                self.data.update(current)
            return self.data

    async def async_write_percent(self, address: int, value: int) -> None:
        if address in SLOT_REGISTERS:
            raise HomeAssistantError(
                f"Register {address} belongs to a time slot and must be written with the slot"
            )
        await self._write_and_confirm(address, f"{int(value)}")

    async def async_write_switch(self, address: int, enabled: bool) -> None:
        if address in SLOT_REGISTERS:
            raise HomeAssistantError(
                f"Register {address} belongs to a time slot and must be written with the slot"
            )
        await self._write_and_confirm(address, "1" if enabled else "0")

    async def _write_and_confirm(self, address: int, decimal_value: str) -> None:
        expected = int(decimal_value)
        async with self._write_lock:
            try:
                await self.client.async_write_register(
                    target="inverter",
                    device_id=self.inverter_id,
                    register=address,
                    value=decimal_value,
                    fmt="dec",
                )
                actual = await self.client.async_read_register(
                    target="inverter",
                    device_id=self.inverter_id,
                    register=address,
                )
            except GrottApiError as err:
                raise HomeAssistantError(str(err)) from err
            self._store({address: actual})
            if int(actual, 16) != expected:
                raise HomeAssistantError(
                    f"Register {address} is still {actual}, not {expected}"
                )

    async def async_write_slot(
        self,
        schedule: str,
        slot: int,
        *,
        hour: int | None = None,
        minute: int | None = None,
        which: str | None = None,
        enabled: bool | None = None,
        start: str | None = None,
        stop: str | None = None,
    ) -> None:
        """Change one part of a slot, sending all three registers together."""
        start_addr, stop_addr, enable_addr = slot_registers(schedule, slot)
        new_clock: str | None = None
        if which in ("start", "end"):
            if hour is None or minute is None:
                raise HomeAssistantError(f"{which} time is missing")
            new_clock = encode_time(hour, minute)
        async with self._write_lock:
            start_hex = start if start is not None else self._require(start_addr)
            stop_hex = stop if stop is not None else self._require(stop_addr)
            if which == "start" and new_clock is not None:
                start_hex = new_clock
            elif which == "end" and new_clock is not None:
                stop_hex = new_clock
            if enabled is None:
                enable_hex = self._require(enable_addr)
            else:
                enable_hex = encode_enable(enabled)
            packed = pack_slot(start_hex, stop_hex, enable_hex)
            expected = {
                start_addr: normalize_hex(start_hex),
                stop_addr: normalize_hex(stop_hex),
                enable_addr: normalize_hex(enable_hex),
            }
            try:
                await self.client.async_write_slot(self.inverter_id, start_addr, packed)
                actual = {}
                for address in (start_addr, stop_addr, enable_addr):
                    actual[address] = await self.client.async_read_register(
                        target="inverter",
                        device_id=self.inverter_id,
                        register=address,
                    )
            except GrottApiError as err:
                raise HomeAssistantError(str(err)) from err
            self._store(actual)
            if actual != expected:
                raise HomeAssistantError(
                    "The inverter kept the previous slot. A window that contains "
                    "the current time is rejected, and the three slot registers "
                    "have to change together."
                )
        _LOGGER.info(
            "Set %s slot %s to %s-%s enabled=%s",
            schedule,
            slot,
            expected[start_addr],
            expected[stop_addr],
            decode_enable(expected[enable_addr]),
        )

    async def async_read_any(
        self, target: str, register: int, fmt: str
    ) -> dict[str, Any]:
        async with self._write_lock:
            return await self._read_any(target, register, fmt)

    async def async_write_any(
        self, target: str, register: int, value: str, fmt: str
    ) -> dict[str, Any]:
        if target == "inverter" and register in SLOT_REGISTERS:
            raise HomeAssistantError(
                f"Register {register} is part of a time slot. Use write_slot "
                "so start, stop, and enable are sent in one call."
            )
        device_id = self._device_id(target)
        read_format = "hex" if target == "inverter" else "text"
        async with self._write_lock:
            try:
                await self.client.async_write_register(
                    target=target,
                    device_id=device_id,
                    register=register,
                    value=value,
                    fmt=fmt if target == "inverter" else "text",
                )
            except GrottApiError as err:
                raise HomeAssistantError(str(err)) from err
            result = await self._read_any(target, register, read_format)
        if target == "inverter" and fmt in ("dec", "hex"):
            base = 16 if fmt == "hex" else 10
            try:
                expected = int(value, base)
                actual = int(result["value"], 16)
            except ValueError as err:
                raise HomeAssistantError(f"Register {register} readback was not numeric") from err
            if actual != expected:
                raise HomeAssistantError(
                    f"Register {register} is still {result['value']}, not {value}"
                )
        return result

    async def async_write_raw_multi(
        self, start: int, end: int, value: str
    ) -> list[dict[str, Any]]:
        """Write concatenated hex words, then read each register back."""
        async with self._write_lock:
            try:
                await self.client.async_write_multi(self.inverter_id, start, end, value)
            except GrottApiError as err:
                raise HomeAssistantError(str(err)) from err
            readback = []
            stored: dict[int, str] = {}
            for address in range(start, end + 1):
                item = await self._read_any("inverter", address, "hex", store=False)
                readback.append(item)
                stored[address] = str(item["value"])
            self._store(stored)
            return readback

    async def _read_any(
        self, target: str, register: int, fmt: str, *, store: bool = True
    ) -> dict[str, Any]:
        device_id = self._device_id(target)
        try:
            value = await self.client.async_read_register(
                target=target,
                device_id=device_id,
                register=register,
                fmt=fmt,
            )
        except GrottApiError as err:
            raise HomeAssistantError(str(err)) from err
        result: dict[str, Any] = {
            "target": target,
            "device_id": device_id,
            "register": register,
            "format": fmt,
            "value": value,
        }
        if fmt == "hex":
            try:
                normalized = normalize_hex(value)
                result["value"] = normalized
                result["decimal"] = int(normalized, 16)
            except ValueError:
                pass
        if store and target == "inverter" and fmt == "hex" and "decimal" in result:
            self._store({register: str(result["value"])})
        return result

    def _device_id(self, target: str) -> str:
        if target == "inverter":
            return self.inverter_id
        if target == "datalogger":
            if not self.datalogger_id:
                raise HomeAssistantError("This entry has no datalogger serial")
            return self.datalogger_id
        raise HomeAssistantError("target must be inverter or datalogger")

    def _require(self, address: int) -> str:
        value = self.raw(address)
        if value is None:
            raise HomeAssistantError(
                f"Register {address} has not been read yet. Refresh, then try again."
            )
        return normalize_hex(value)

    def _store(self, updates: dict[int, str]) -> None:
        # Mutate the live map. Replacing it would lose a write when a poll
        # assigns its in-flight result a moment later.
        data = self.data
        if data is None:
            data = {}
            self.data = data
        data.update(updates)
        self.async_set_updated_data(data)


