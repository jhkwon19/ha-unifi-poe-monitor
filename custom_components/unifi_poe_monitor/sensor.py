"""PoE power sensors for a single UniFi switch device."""

from __future__ import annotations

from math import isfinite
from time import monotonic

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PoECoordinator
from .api import poe_ports, port_power, total_power
from .const import DOMAIN, SCAN_INTERVAL_SECONDS


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create port power, total power, and cumulative energy sensors."""
    coordinator: PoECoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [PoEPortSensor(coordinator, index) for index in poe_ports(coordinator.data)]
        + [PoETotalSensor(coordinator), PoEEnergySensor(coordinator)]
    )


def switch_device_info(coordinator: PoECoordinator) -> DeviceInfo:
    """Register every sensor under one switch device."""
    device = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.mac)},
        name=device.get("name") or device.get("model") or "UniFi PoE Switch",
        manufacturer="Ubiquiti",
        model=device.get("model"),
        sw_version=device.get("version"),
        connections={("mac", device["mac"])},
    )


class PoEBaseSensor(CoordinatorEntity[PoECoordinator], SensorEntity):
    """Common sensor identity and device registration."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(self, coordinator: PoECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = switch_device_info(coordinator)


class PoEPortSensor(PoEBaseSensor):
    """Measured PoE power from one physical port."""

    def __init__(self, coordinator: PoECoordinator, port_index: int) -> None:
        super().__init__(coordinator)
        self._port_index = port_index
        self._attr_unique_id = f"{coordinator.mac}_port_{port_index}_poe_power"
        self._attr_name = f"Port {port_index} PoE power"

    @property
    def native_value(self) -> float | None:
        """Return the port reading, if the controller reports one."""
        return port_power(poe_ports(self.coordinator.data).get(self._port_index))

    @property
    def available(self) -> bool:
        """Only expose a reading reported by the controller."""
        return super().available and self.native_value is not None


class PoETotalSensor(PoEBaseSensor):
    """Report the switch's total PoE output."""

    def __init__(self, coordinator: PoECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_total_poe_power"
        self._attr_name = "Total PoE power"

    @property
    def native_value(self) -> float | None:
        """Return the switch's total PoE output in watts."""
        return total_power(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Avoid reporting a missing total."""
        return super().available and self.native_value is not None


class PoEEnergySensor(CoordinatorEntity[PoECoordinator], RestoreSensor):
    """Integrate measured PoE output power into cumulative kWh."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_has_entity_name = True

    def __init__(self, coordinator: PoECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = switch_device_info(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_total_poe_energy"
        self._attr_name = "Total PoE energy"
        self._energy_kwh = 0.0
        self._last_power: float | None = None
        self._last_sample: float | None = None

    @property
    def native_value(self) -> float:
        """Return cumulative PoE output energy in kWh."""
        return round(self._energy_kwh, 6)

    async def async_added_to_hass(self) -> None:
        """Restore the total and start measuring from the first live sample."""
        await super().async_added_to_hass()
        restored = await self.async_get_last_sensor_data()
        if restored is not None:
            try:
                value = float(restored.native_value)
            except (TypeError, ValueError):
                value = 0.0
            if isfinite(value) and value >= 0:
                self._energy_kwh = value
        self._last_power = total_power(self.coordinator.data)
        if self._last_power is not None:
            self._last_sample = monotonic()
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Integrate adjacent valid samples without filling outages."""
        now = monotonic()
        power = total_power(self.coordinator.data) if self.coordinator.last_update_success else None
        if power is not None and self._last_power is not None and self._last_sample is not None:
            elapsed = now - self._last_sample
            if 0 < elapsed <= 4 * SCAN_INTERVAL_SECONDS:
                self._energy_kwh += (self._last_power + power) * elapsed / 7_200_000
        self._last_power = power
        self._last_sample = now if power is not None else None
        self.async_write_ha_state()
