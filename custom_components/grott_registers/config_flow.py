"""Config flow for Grott Registers."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GrottApiError, GrottClient
from .codec import inverters_from_payload
from .const import (
    CONF_DATALOGGER,
    CONF_EXTENDED,
    CONF_INVERTER,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


class GrottConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect to grottserver and pick the inverter."""

    VERSION = 1

    def __init__(self) -> None:
        self._host = ""
        self._port = DEFAULT_PORT
        self._inverters: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            self._port = user_input[CONF_PORT]
            try:
                payload = await GrottClient(
                    async_get_clientsession(self.hass), self._host, self._port
                ).async_list_inverters()
            except GrottApiError:
                errors["base"] = "cannot_connect"
            else:
                self._inverters = inverters_from_payload(payload)
                if not self._inverters:
                    return await self.async_step_manual()
                if len(self._inverters) == 1:
                    return await self._create(next(iter(self._inverters)))
                return await self.async_step_inverter()

        schema = DATA_SCHEMA
        if self._host:
            schema = self.add_suggested_values_to_schema(
                DATA_SCHEMA, {CONF_HOST: self._host, CONF_PORT: self._port}
            )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_inverter(self, user_input: dict[str, Any] | None = None):
        serials = sorted(self._inverters)
        if user_input is not None:
            return await self._create(user_input[CONF_INVERTER])
        return self.async_show_form(
            step_id="inverter",
            data_schema=vol.Schema(
                {vol.Required(CONF_INVERTER, default=serials[0]): vol.In(serials)}
            ),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            serial = user_input[CONF_INVERTER].strip()
            if not serial:
                errors["base"] = "invalid_inverter"
            else:
                return await self._create(serial)
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_INVERTER): str}),
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            try:
                payload = await GrottClient(
                    async_get_clientsession(self.hass), host, port
                ).async_list_inverters()
            except GrottApiError:
                errors["base"] = "cannot_connect"
            else:
                found = inverters_from_payload(payload)
                datalogger = found.get(entry.data[CONF_INVERTER], entry.data.get(CONF_DATALOGGER, ""))
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_DATALOGGER: datalogger,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): cv.port,
                }
            ),
            errors=errors,
        )

    async def _create(self, inverter_id: str):
        await self.async_set_unique_id(inverter_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Grott {inverter_id}",
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_INVERTER: inverter_id,
                CONF_DATALOGGER: self._inverters.get(inverter_id, ""),
            },
            options={
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_EXTENDED: False,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GrottOptionsFlow:
        return GrottOptionsFlow()


class GrottOptionsFlow(OptionsFlow):
    """Scan interval and the optional extra slots."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Required(
                        CONF_EXTENDED,
                        default=options.get(CONF_EXTENDED, False),
                    ): bool,
                }
            ),
        )
