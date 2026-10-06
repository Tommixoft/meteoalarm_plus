"""Event entity announcing issued, updated and ended alerts."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import AlertChange
from .coordinator import MeteoAlarmConfigEntry, MeteoAlarmCoordinator, MeteoAlarmData
from .entity import MeteoAlarmEntity, alert_summary

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MeteoAlarmChangeEvent(entry.runtime_data, "alert_change")])


class MeteoAlarmChangeEvent(MeteoAlarmEntity, EventEntity):
    """Fires once per alert that appears, is replaced, or ends."""

    _attr_event_types = [change.value for change in AlertChange]

    def __init__(self, coordinator: MeteoAlarmCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._handled_data: MeteoAlarmData | None = coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        # Listeners are also notified when a poll fails, with the previous snapshot still in place;
        # its changes were already announced and must not fire again.
        data = self.coordinator.data
        if data is self._handled_data or not data.changes:
            self._handled_data = data
            super()._handle_coordinator_update()
            return
        self._handled_data = data
        for change, alert in data.changes:
            self._trigger_event(change.value, alert_summary(alert))
            self.async_write_ha_state()
