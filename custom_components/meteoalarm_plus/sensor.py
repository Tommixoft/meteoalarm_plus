"""Sensors for the highest awareness level and the list of relevant alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SELECTABLE_MIN_LEVELS
from .coordinator import MeteoAlarmConfigEntry
from .entity import MeteoAlarmEntity, alert_summary

PARALLEL_UPDATES = 0

NO_ALERT = "none"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MeteoAlarmHighestLevelSensor(coordinator, "highest_level"),
            MeteoAlarmCountSensor(coordinator, "alert_count"),
        ]
    )


class MeteoAlarmHighestLevelSensor(MeteoAlarmEntity, SensorEntity):
    """Awareness level of the most dangerous relevant alert."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [NO_ALERT, *SELECTABLE_MIN_LEVELS]

    @property
    def native_value(self) -> str:
        highest = self.coordinator.data.highest
        if highest is None:
            return NO_ALERT
        return highest.level.slug


class MeteoAlarmCountSensor(MeteoAlarmEntity, SensorEntity):
    """Number of relevant alerts, with all of them listed in the attributes."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"alerts"})

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"alerts": [alert_summary(alert) for alert in self.coordinator.data.alerts]}
