"""API-key configuration for UniFi PoE Monitor."""

from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant import config_entries

from .api import UniFiAPIError, UniFiAuthError, UniFiClient, normalize_mac, poe_ports
from .const import DOMAIN


class UniFiPoEFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Connect to a controller and choose a 16-port PoE switch."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection: dict = {}
        self._switches: dict[str, dict] = {}

    async def async_step_user(self, user_input: dict | None = None):
        errors = {}
        if user_input is not None:
            connection = dict(user_input)
            connection["host"] = connection["host"].strip().rstrip("/")
            if not connection["host"].startswith(("http://", "https://")):
                errors["base"] = "invalid_host"
            else:
                client = UniFiClient(**connection)
                try:
                    devices = await client.devices()
                except UniFiAuthError:
                    errors["base"] = "invalid_auth"
                except (aiohttp.ClientError, TimeoutError, UniFiAPIError, ValueError):
                    errors["base"] = "cannot_connect"
                else:
                    self._switches = {
                        normalize_mac(device["mac"]): device
                        for device in devices
                        if device.get("type") == "usw"
                        and isinstance(device.get("mac"), str)
                        and isinstance(device.get("port_table"), list)
                        and len(device["port_table"]) == 16
                        and poe_ports(device)
                    }
                    if self._switches:
                        self._connection = connection
                        return await self.async_step_switch()
                    errors["base"] = "no_switches"
                finally:
                    await client.close()
        schema = vol.Schema({
            vol.Required("host", default="https://unifi.local"): str,
            vol.Required("api_key"): str,
            vol.Required("site", default="default"): str,
            vol.Required("verify_ssl", default=True): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_switch(self, user_input: dict | None = None):
        if user_input is not None:
            mac = user_input["mac"]
            if mac in self._switches:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                device = self._switches[mac]
                return self.async_create_entry(
                    title=device.get("name") or device.get("model") or mac,
                    data={**self._connection, "mac": mac},
                )
        options = {
            mac: f"{device.get('name') or device.get('model') or 'Switch'} ({device.get('mac')})"
            for mac, device in self._switches.items()
        }
        return self.async_show_form(
            step_id="switch",
            data_schema=vol.Schema({vol.Required("mac"): vol.In(options)}),
        )
