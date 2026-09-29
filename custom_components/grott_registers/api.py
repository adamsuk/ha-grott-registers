"""HTTP client for the grottserver register API on port 5782."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .codec import normalize_hex

_LOGGER = logging.getLogger(__name__)

READ_ATTEMPTS = 3


class GrottApiError(Exception):
    """grottserver rejected a call or never answered."""


class GrottClient:
    """Talks to one grottserver. The session is owned by Home Assistant."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"

    async def async_list_inverters(self) -> dict[str, Any]:
        """Return the raw GET /inverter payload."""
        text = await self._request("GET", "/inverter", {})
        return _json_object(text)

    async def async_read_register(
        self,
        *,
        target: str,
        device_id: str,
        register: int,
        fmt: str = "hex",
        attempts: int = READ_ATTEMPTS,
    ) -> str:
        """Read one register. Inverter results are returned as 4-digit hex."""
        last_error: GrottApiError | None = None
        for attempt in range(attempts):
            try:
                return await self._read_once(target, device_id, register, fmt)
            except GrottApiError as err:
                last_error = err
                _LOGGER.debug(
                    "Read %s register %s failed (%s/%s): %s",
                    target,
                    register,
                    attempt + 1,
                    attempts,
                    err,
                )
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5)
        assert last_error is not None
        raise last_error

    async def async_write_register(
        self,
        *,
        target: str,
        device_id: str,
        register: int,
        value: str,
        fmt: str = "dec",
    ) -> None:
        """Write one register. Do not use this for a time-slot address."""
        path, id_key = _target(target)
        await self._request(
            "PUT",
            path,
            {
                "command": "register",
                id_key: device_id,
                "register": str(register),
                "value": value,
                "format": fmt,
            },
        )

    async def async_write_multi(
        self, inverter_id: str, start: int, end: int, packed_hex: str
    ) -> None:
        """Write a contiguous run of registers. The value is concatenated hex words."""
        words = end - start + 1
        if words < 1:
            raise GrottApiError("end register is before the start register")
        if len(packed_hex) != words * 4:
            raise GrottApiError(
                f"expected {words * 4} hex characters for registers {start}-{end}"
            )
        for offset in range(0, len(packed_hex), 4):
            normalize_hex(packed_hex[offset : offset + 4])
        await self._request(
            "PUT",
            "/inverter",
            {
                "command": "multiregister",
                "inverter": inverter_id,
                "startregister": str(start),
                "endregister": str(end),
                "value": packed_hex.lower(),
            },
        )

    async def async_write_slot(
        self, inverter_id: str, start: int, packed_hex: str
    ) -> None:
        """Write start, stop, and enable in one multiregister call."""
        await self.async_write_multi(inverter_id, start, start + 2, packed_hex)

    async def _read_once(
        self, target: str, device_id: str, register: int, fmt: str
    ) -> str:
        path, id_key = _target(target)
        text = await self._request(
            "GET",
            path,
            {
                "command": "register",
                id_key: device_id,
                "register": str(register),
                "format": fmt,
            },
        )
        payload = _json_object(text)
        if "value" not in payload:
            raise GrottApiError(f"register {register} response had no value")
        raw = str(payload["value"])
        if target == "inverter" and fmt == "hex":
            return normalize_hex(raw)
        return raw

    async def _request(self, method: str, path: str, params: dict[str, str]) -> str:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                text = (await response.text()).strip()
                if response.status >= 400:
                    raise GrottApiError(text or f"HTTP {response.status}")
                return text
        except GrottApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GrottApiError(f"cannot reach grottserver: {err}") from err


def _target(target: str) -> tuple[str, str]:
    if target == "inverter":
        return "/inverter", "inverter"
    if target == "datalogger":
        return "/datalogger", "datalogger"
    raise GrottApiError("target must be inverter or datalogger")


def _json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as err:
        raise GrottApiError(f"grottserver returned non-JSON: {text[:120]}") from err
    if not isinstance(payload, dict):
        raise GrottApiError("grottserver JSON was not an object")
    return payload
