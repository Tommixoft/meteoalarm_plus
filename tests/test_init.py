"""Tests for entity states driven by the coordinator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.meteoalarm_plus.const import (
    CONF_IGNORE_UPCOMING,
    CONF_IGNORED_TYPES,
    CONF_MIN_LEVEL,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.meteoalarm_plus.diagnostics import async_get_config_entry_diagnostics

from .conftest import LITHUANIA_URL, make_entry

# Feed snapshot: the only LT010 alert is yellow fog from 21:30 until 04:59:59 next day (UTC).
BEFORE_FOG = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
FOG_ONSET = datetime(2026, 10, 6, 21, 30, tzinfo=UTC)
FOG_EXPIRES = datetime(2026, 10, 7, 4, 59, 59, tzinfo=UTC)


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    registry = er.async_get(hass)
    found = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert found is not None
    return found


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def move_time(hass: HomeAssistant, freezer: FrozenDateTimeFactory, moment: datetime) -> None:
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_feed")
async def test_upcoming_alert_is_reported_by_default(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, config_entry: MockConfigEntry
) -> None:
    freezer.move_to(BEFORE_FOG)
    await setup_entry(hass, config_entry)

    alert = hass.states.get(entity_id(hass, config_entry, "binary_sensor", "alert"))
    assert alert.state == STATE_ON
    assert alert.attributes["level"] == "yellow"
    assert alert.attributes["alert_type"] == "fog"
    assert alert.attributes["event"] == "Dangerous fog"
    assert (
        hass.states.get(entity_id(hass, config_entry, "sensor", "highest_level")).state == "yellow"
    )
    count = hass.states.get(entity_id(hass, config_entry, "sensor", "alert_count"))
    assert count.state == "1"
    assert [item["alert_type"] for item in count.attributes["alerts"]] == ["fog"]
    assert (
        hass.states.get(entity_id(hass, config_entry, "event", "alert_change")).state
        == STATE_UNKNOWN
    )


@pytest.mark.usefixtures("mock_feed")
async def test_alert_attributes_match_core_meteoalarm_for_lovelace_cards(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, config_entry: MockConfigEntry
) -> None:
    freezer.move_to(BEFORE_FOG)
    await setup_entry(hass, config_entry)

    attributes = hass.states.get(entity_id(hass, config_entry, "binary_sensor", "alert")).attributes

    assert attributes["attribution"] == "Information provided by MeteoAlarm"
    assert attributes["awareness_level"] == "2; yellow; Moderate"
    assert attributes["awareness_type"] == "4; Fog"
    assert attributes["severity"] == "Moderate"
    assert attributes["senderName"]
    assert attributes["effective"]
    assert not {"status", "state", "id", "category"} & attributes.keys()


@pytest.mark.usefixtures("mock_feed")
async def test_ignored_type_hides_alert(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(BEFORE_FOG)
    config_entry = make_entry({CONF_IGNORED_TYPES: ["fog"]})
    await setup_entry(hass, config_entry)

    assert (
        hass.states.get(entity_id(hass, config_entry, "binary_sensor", "alert")).state == STATE_OFF
    )
    assert hass.states.get(entity_id(hass, config_entry, "sensor", "highest_level")).state == "none"
    assert hass.states.get(entity_id(hass, config_entry, "sensor", "alert_count")).state == "0"


@pytest.mark.usefixtures("mock_feed")
async def test_min_level_hides_lower_alerts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(BEFORE_FOG)
    config_entry = make_entry({CONF_MIN_LEVEL: "orange"})
    await setup_entry(hass, config_entry)

    assert (
        hass.states.get(entity_id(hass, config_entry, "binary_sensor", "alert")).state == STATE_OFF
    )


async def test_onset_switches_state_without_polling(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_feed: AiohttpClientMocker
) -> None:
    freezer.move_to(FOG_ONSET - timedelta(minutes=30))
    config_entry = make_entry({CONF_IGNORE_UPCOMING: True, CONF_SCAN_INTERVAL: 120})
    await setup_entry(hass, config_entry)
    alert_id = entity_id(hass, config_entry, "binary_sensor", "alert")
    event_id = entity_id(hass, config_entry, "event", "alert_change")
    assert hass.states.get(alert_id).state == STATE_OFF

    await move_time(hass, freezer, FOG_ONSET + timedelta(seconds=2))

    assert hass.states.get(alert_id).state == STATE_ON
    assert hass.states.get(event_id).attributes["event_type"] == "alert_issued"
    assert mock_feed.call_count == 1


async def test_expiry_switches_state_without_polling(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_feed: AiohttpClientMocker
) -> None:
    freezer.move_to(FOG_EXPIRES - timedelta(minutes=30))
    config_entry = make_entry({CONF_SCAN_INTERVAL: 120})
    await setup_entry(hass, config_entry)
    alert_id = entity_id(hass, config_entry, "binary_sensor", "alert")
    assert hass.states.get(alert_id).state == STATE_ON

    await move_time(hass, freezer, FOG_EXPIRES + timedelta(seconds=2))

    assert hass.states.get(alert_id).state == STATE_OFF
    event = hass.states.get(entity_id(hass, config_entry, "event", "alert_change"))
    assert event.attributes["event_type"] == "alert_ended"
    assert event.attributes["alert_type"] == "fog"
    assert mock_feed.call_count == 1


async def test_failed_poll_does_not_repeat_events(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    lithuania_payload: dict,
) -> None:
    aioclient_mock.get(LITHUANIA_URL, json=lithuania_payload)
    freezer.move_to(FOG_ONSET - timedelta(minutes=1))
    config_entry = make_entry({CONF_IGNORE_UPCOMING: True})
    await setup_entry(hass, config_entry)
    event_id = entity_id(hass, config_entry, "event", "alert_change")
    await move_time(hass, freezer, FOG_ONSET + timedelta(seconds=2))
    issued_at = hass.states.get(event_id).state

    aioclient_mock.clear_requests()
    aioclient_mock.get(LITHUANIA_URL, status=500)
    await move_time(hass, freezer, FOG_ONSET + timedelta(minutes=11))
    assert hass.states.get(event_id).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(LITHUANIA_URL, json=lithuania_payload)
    await move_time(hass, freezer, FOG_ONSET + timedelta(minutes=22))
    assert hass.states.get(event_id).state == issued_at


@pytest.mark.usefixtures("mock_feed")
async def test_entities_unavailable_when_feed_fails(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    freezer.move_to(BEFORE_FOG)
    await setup_entry(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(LITHUANIA_URL, status=500)
    await move_time(hass, freezer, BEFORE_FOG + timedelta(minutes=11))

    assert (
        hass.states.get(entity_id(hass, config_entry, "binary_sensor", "alert")).state
        == STATE_UNAVAILABLE
    )


async def test_setup_retries_when_feed_unreachable(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(LITHUANIA_URL, status=503)
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("mock_feed")
async def test_unload(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    await setup_entry(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.usefixtures("mock_feed")
async def test_diagnostics_include_feed_and_selection(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, config_entry: MockConfigEntry
) -> None:
    freezer.move_to(BEFORE_FOG)
    await setup_entry(hass, config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert len(diagnostics["feed"]["warnings"]) == 14
    assert [alert["alert_type"] for alert in diagnostics["selected_alerts"]] == ["fog"]
