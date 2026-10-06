"""Binary sensor reporting whether any relevant MeteoAlarm alert is active."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MeteoAlarmConfigEntry
from .entity import MeteoAlarmEntity, alert_details

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MeteoAlarmActiveBinarySensor(entry.runtime_data, "alert")])


class MeteoAlarmActiveBinarySensor(MeteoAlarmEntity, BinarySensorEntity):
    """On while at least one alert passes the configured filters."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        highest = self.coordinator.data.highest
        if highest is None:
            return {}
        return alert_details(highest)
