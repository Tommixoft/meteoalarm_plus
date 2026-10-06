"""HTTP client for the MeteoAlarm warnings feed."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MeteoAlarmError(Exception):
    """The MeteoAlarm feed could not be retrieved."""


class MeteoAlarmCountryNotFound(MeteoAlarmError):
    """MeteoAlarm has no feed for the requested country."""


class MeteoAlarmClient:
    """Fetches the raw warnings feed for one country."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_warnings(self, country: str) -> dict[str, Any]:
        url = API_URL.format(country=country)
        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as response:
                if response.status == HTTPStatus.NOT_FOUND:
                    raise MeteoAlarmCountryNotFound(f"No MeteoAlarm feed for '{country}'")
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise MeteoAlarmError(f"Error fetching {url}: {err}") from err

        if not isinstance(payload, dict) or not isinstance(payload.get("warnings"), list):
            raise MeteoAlarmError(f"Unexpected response format from {url}")
        return payload
