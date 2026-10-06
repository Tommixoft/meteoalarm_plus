"""Diagnostics for MeteoAlarm Plus. The feed is public, so nothing is redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import MeteoAlarmConfigEntry
from .entity import alert_summary


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MeteoAlarmConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "selected_alerts": [alert_summary(alert) for alert in coordinator.data.alerts],
        "feed": coordinator.last_payload,
    }
