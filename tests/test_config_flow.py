"""Tests for the config, reconfigure and options flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.meteoalarm_plus.const import (
    CONF_COUNTRY,
    CONF_IGNORE_UPCOMING,
    CONF_IGNORED_TYPES,
    CONF_LANGUAGE,
    CONF_MIN_LEVEL,
    CONF_REGIONS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .conftest import LITHUANIA_URL


async def start_user_flow(hass: HomeAssistant, country: str = "lithuania") -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_COUNTRY: country}
    )


@pytest.mark.usefixtures("mock_feed")
async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await start_user_flow(hass)
    assert result["step_id"] == "regions"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGIONS: [" lt010", "LT009"], CONF_LANGUAGE: "lt-LT"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MeteoAlarm Lithuania (Utena county, Vilnius county)"
    assert result["data"] == {
        CONF_COUNTRY: "lithuania",
        CONF_REGIONS: ["LT009", "LT010"],
        CONF_LANGUAGE: "lt-LT",
    }
    assert result["result"].unique_id == "lithuania_LT009_LT010"


@pytest.mark.usefixtures("mock_feed")
async def test_regions_step_offers_regions_seen_in_feed(hass: HomeAssistant) -> None:
    result = await start_user_flow(hass)

    selector = result["data_schema"].schema[CONF_REGIONS].config
    values = [option["value"] for option in selector["options"]]
    assert "LT010" in values
    assert values == sorted(values)


@pytest.mark.usefixtures("mock_feed")
async def test_invalid_region_shows_error(hass: HomeAssistant) -> None:
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGIONS: ["Vilnius"], CONF_LANGUAGE: "en-GB"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REGIONS: "invalid_region"}


async def test_unreachable_feed_shows_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(LITHUANIA_URL, status=502)

    result = await start_user_flow(hass)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_unknown_country_shows_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(LITHUANIA_URL, status=404)

    result = await start_user_flow(hass)

    assert result["errors"] == {CONF_COUNTRY: "unknown_country"}


@pytest.mark.usefixtures("mock_feed")
async def test_duplicate_entry_aborts(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGIONS: ["LT010"], CONF_LANGUAGE: "en-GB"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_feed")
async def test_reconfigure_changes_regions(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_COUNTRY: "lithuania"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGIONS: ["LT001"], CONF_LANGUAGE: "en-GB"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_REGIONS] == ["LT001"]
    assert config_entry.unique_id == "lithuania_LT001"


@pytest.mark.usefixtures("mock_feed")
async def test_reconfigure_to_existing_entry_aborts(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="lithuania_LT001",
        data={CONF_COUNTRY: "lithuania", CONF_REGIONS: ["LT001"], CONF_LANGUAGE: "en-GB"},
    )
    other.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_COUNTRY: "lithuania"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGIONS: ["LT001"], CONF_LANGUAGE: "en-GB"}
    )

    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_REGIONS] == ["LT010"]


@pytest.mark.usefixtures("mock_feed")
async def test_options_flow_saves_filters(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MIN_LEVEL: "orange",
            CONF_IGNORED_TYPES: ["fog", "rain"],
            CONF_IGNORE_UPCOMING: True,
            CONF_SCAN_INTERVAL: 15.0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        CONF_MIN_LEVEL: "orange",
        CONF_IGNORED_TYPES: ["fog", "rain"],
        CONF_IGNORE_UPCOMING: True,
        CONF_SCAN_INTERVAL: 15,
    }
    assert config_entry.runtime_data.alert_filter.min_level.slug == "orange"
