"""Data update coordinator for MeteoAlarm Plus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .alerts import Alert, AlertFilter, diff_alerts, next_transition, parse_warnings, select_alerts
from .api import MeteoAlarmClient, MeteoAlarmError
from .const import (
    CONF_COUNTRY,
    CONF_IGNORE_UPCOMING,
    CONF_IGNORED_TYPES,
    CONF_LANGUAGE,
    CONF_MIN_LEVEL,
    CONF_REGIONS,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_LEVEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    AlertChange,
    AwarenessLevel,
)

_LOGGER = logging.getLogger(__name__)

# Fire slightly after an onset/expiry moment so the comparison with "now" has flipped.
TRANSITION_MARGIN = timedelta(seconds=1)

type MeteoAlarmConfigEntry = ConfigEntry[MeteoAlarmCoordinator]


@dataclass(frozen=True, slots=True)
class MeteoAlarmData:
    """Snapshot of relevant alerts and what changed since the previous snapshot."""

    alerts: tuple[Alert, ...]
    changes: tuple[tuple[AlertChange, Alert], ...]

    @property
    def highest(self) -> Alert | None:
        return self.alerts[0] if self.alerts else None


class MeteoAlarmCoordinator(DataUpdateCoordinator[MeteoAlarmData]):
    """Polls the country feed and re-evaluates alerts when one starts or expires."""

    config_entry: MeteoAlarmConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MeteoAlarmConfigEntry) -> None:
        options = entry.options
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_COUNTRY]}",
            update_interval=timedelta(
                minutes=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds() / 60)
            ),
        )
        self.client = MeteoAlarmClient(async_get_clientsession(hass))
        self.country: str = entry.data[CONF_COUNTRY]
        self.language: str = entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        self.alert_filter = AlertFilter(
            regions=frozenset(entry.data[CONF_REGIONS]),
            min_level=AwarenessLevel.from_slug(options.get(CONF_MIN_LEVEL, DEFAULT_MIN_LEVEL)),
            ignored_types=frozenset(options.get(CONF_IGNORED_TYPES, [])),
            ignore_upcoming=options.get(CONF_IGNORE_UPCOMING, False),
        )
        self.last_payload: dict[str, Any] | None = None
        self._all_alerts: list[Alert] = []
        self._unsub_transition: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> MeteoAlarmData:
        try:
            payload = await self.client.async_get_warnings(self.country)
        except MeteoAlarmError as err:
            raise UpdateFailed(str(err)) from err

        self.last_payload = payload
        self._all_alerts = parse_warnings(payload, self.language)
        return self._evaluate(dt_util.utcnow())

    async def async_shutdown(self) -> None:
        self._cancel_transition()
        await super().async_shutdown()

    def _evaluate(self, now: datetime) -> MeteoAlarmData:
        alerts = tuple(select_alerts(self._all_alerts, self.alert_filter, now))
        # No change events on the first evaluation: a restart must not re-announce known alerts.
        changes = tuple(diff_alerts(self.data.alerts, alerts)) if self.data is not None else ()
        self._schedule_transition(now)
        return MeteoAlarmData(alerts=alerts, changes=changes)

    def _schedule_transition(self, now: datetime) -> None:
        self._cancel_transition()
        moment = next_transition(self._all_alerts, self.alert_filter, now)
        if moment is not None:
            self._unsub_transition = async_track_point_in_utc_time(
                self.hass, self._handle_transition, moment + TRANSITION_MARGIN
            )

    @callback
    def _handle_transition(self, now: datetime) -> None:
        # Not async_set_updated_data: that would postpone the next poll and mark a failing feed as healthy.
        self._unsub_transition = None
        self.data = self._evaluate(now)
        self.async_update_listeners()

    def _cancel_transition(self) -> None:
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None
