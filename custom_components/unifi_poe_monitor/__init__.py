"""UniFi PoE Monitor integration."""

from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UniFiAPIError, UniFiAuthError, UniFiClient, normalize_mac
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)


class PoECoordinator(DataUpdateCoordinator[dict]):
    """Poll one switch's current telemetry."""

    def __init__(self, hass: HomeAssistant, client: UniFiClient, mac: str) -> None:
        super().__init__(
            hass, logger=_LOGGER,
            name=DOMAIN, update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.mac = mac

    async def _async_update_data(self) -> dict:
        try:
            devices = await self.client.devices()
        except (aiohttp.ClientError, TimeoutError, UniFiAuthError, UniFiAPIError) as err:
            raise UpdateFailed(str(err)) from err
        for device in devices:
            if normalize_mac(str(device.get("mac", ""))) == self.mac:
                if device.get("state") != 1:
                    raise UpdateFailed("Switch is offline")
                return device
        raise UpdateFailed("Switch was not found in UniFi Network")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one selected switch."""
    client = UniFiClient(
        entry.data["host"], entry.data["api_key"], entry.data["site"],
        entry.data["verify_ssl"],
    )
    coordinator = PoECoordinator(hass, client, entry.data["mac"])
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors and close the API session."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.client.close()
    return True
