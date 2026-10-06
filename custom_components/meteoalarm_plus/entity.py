"""Base entity and shared alert attribute formatting for MeteoAlarm Plus."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alerts import Alert
from .const import (
    ATTRIBUTION,
    AWARENESS_LEVEL_TEXTS,
    AWARENESS_TYPE_TEXTS,
    CONF_REGIONS,
    DOMAIN,
)
from .coordinator import MeteoAlarmCoordinator

# State attributes share a 16 KiB budget; long free-text fields are cut to keep many alerts within it.
MAX_TEXT_LENGTH = 500


class MeteoAlarmEntity(CoordinatorEntity[MeteoAlarmCoordinator]):
    """Entity bound to one MeteoAlarm Plus config entry."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: MeteoAlarmCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=entry.title,
            manufacturer="MeteoAlarm",
            model=", ".join(sorted(entry.data[CONF_REGIONS])),
            configuration_url="https://meteoalarm.org",
        )


def alert_summary(alert: Alert) -> dict[str, Any]:
    """Compact alert description used in list attributes and events.

    awareness_level / awareness_type keep the core meteoalarm format ("2; yellow; Moderate",
    "4; Fog") that MeteoAlarm cards parse; level / alert_type carry the plain names used by
    this integration's options and sensors.
    """
    return {
        "identifier": alert.identifier,
        "event": alert.event,
        "headline": alert.headline,
        "awareness_level": AWARENESS_LEVEL_TEXTS[alert.level],
        "awareness_type": AWARENESS_TYPE_TEXTS.get(
            alert.type_code, f"{alert.type_code}; {alert.type_name}"
        ),
        "level": alert.level.slug,
        "alert_type": alert.type_slug or str(alert.type_code),
        "severity": alert.severity,
        "onset": alert.onset.isoformat(),
        "expires": alert.expires.isoformat(),
        "regions": sorted(alert.region_ids),
    }


def alert_details(alert: Alert) -> dict[str, Any]:
    """Full alert description, using the attribute names of the core meteoalarm integration.

    Never add status, state, id or category: Lovelace alert cards use those keys to detect
    other providers or to decide whether an alert is active.
    """
    return {
        **alert_summary(alert),
        "description": _truncate(alert.description),
        "instruction": _truncate(alert.instruction),
        "urgency": alert.urgency,
        "certainty": alert.certainty,
        "effective": alert.effective.isoformat(),
        "area": ", ".join(name for _, name in alert.areas),
        "senderName": alert.sender_name,
        "language": alert.language,
        "web": alert.web,
    }


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return text[: MAX_TEXT_LENGTH - 1] + "…"
