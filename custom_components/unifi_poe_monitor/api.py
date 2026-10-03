"""Read-only UniFi Network PoE telemetry client."""

from __future__ import annotations

from math import isfinite
from typing import Any
from urllib.parse import quote

import aiohttp


class UniFiAuthError(Exception):
    """The API key was rejected."""


class UniFiAPIError(Exception):
    """The controller returned unusable data."""


class UniFiClient:
    """Read device statistics using an X-API-Key header."""

    def __init__(self, host: str, api_key: str, site: str, verify_ssl: bool) -> None:
        self._base = host.rstrip("/")
        self._site = site
        self._ssl = None if verify_ssl else False
        self._session = aiohttp.ClientSession(
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=20),
        )

    async def close(self) -> None:
        """Release the HTTP connection."""
        await self._session.close()

    async def devices(self) -> list[dict[str, Any]]:
        """Fetch live device data from the Network application."""
        path = f"/proxy/network/api/s/{quote(self._site, safe='')}/stat/device"
        async with self._session.get(self._base + path, ssl=self._ssl) as response:
            if response.status in (401, 403):
                raise UniFiAuthError("UniFi API key was rejected")
            response.raise_for_status()
            payload = await response.json(content_type=None)
        if not isinstance(payload, dict) or payload.get("meta", {}).get("rc") != "ok":
            raise UniFiAPIError("Unexpected UniFi device response")
        devices = payload.get("data")
        if not isinstance(devices, list):
            raise UniFiAPIError("UniFi device list is missing")
        return [device for device in devices if isinstance(device, dict)]


def normalize_mac(value: str) -> str:
    """Create a stable identifier from a MAC address."""
    return "".join(char for char in value.lower() if char in "0123456789abcdef")


def poe_ports(device: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return the switch's PoE-capable physical ports."""
    result = {}
    for port in device.get("port_table", []):
        if not isinstance(port, dict):
            continue
        index = port.get("port_idx")
        if isinstance(index, int) and 1 <= index <= 16 and (
            port.get("poe_caps", 0) or port.get("port_poe") or "poe_power" in port
        ):
            result[index] = port
    return result


def parse_power(value: Any) -> float | None:
    """Parse a nonnegative watt reading without inventing missing values."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        power = float(value)
    except (TypeError, ValueError):
        return None
    return power if isfinite(power) and 0 <= power < 1000 else None


def port_power(port: dict[str, Any] | None) -> float | None:
    """Read a port's measured PoE output in watts."""
    return parse_power(port.get("poe_power")) if port is not None else None


def total_power(device: dict[str, Any]) -> float | None:
    """Prefer the switch's reported PoE total, falling back to a full sum."""
    reported = parse_power(device.get("total_used_power"))
    if reported is not None:
        return reported
    ports = poe_ports(device)
    if not ports:
        return None
    readings = [port_power(port) for port in ports.values()]
    if any(value is None for value in readings):
        return None
    return round(sum(readings), 3)
