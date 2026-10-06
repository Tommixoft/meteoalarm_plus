"""Shared fixtures for MeteoAlarm Plus tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, load_json_object_fixture
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.meteoalarm_plus.const import (
    API_URL,
    CONF_COUNTRY,
    CONF_LANGUAGE,
    CONF_REGIONS,
    DOMAIN,
)

LITHUANIA_URL = API_URL.format(country="lithuania")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    yield


@pytest.fixture
def lithuania_payload() -> dict[str, Any]:
    return load_json_object_fixture("lithuania.json")


@pytest.fixture
def mock_feed(
    aioclient_mock: AiohttpClientMocker, lithuania_payload: dict[str, Any]
) -> AiohttpClientMocker:
    aioclient_mock.get(LITHUANIA_URL, json=lithuania_payload)
    return aioclient_mock


def make_entry(options: dict[str, Any] | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MeteoAlarm Lithuania (Vilnius county)",
        unique_id="lithuania_LT010",
        data={CONF_COUNTRY: "lithuania", CONF_REGIONS: ["LT010"], CONF_LANGUAGE: "en-GB"},
        options=options or {},
    )


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return make_entry()
