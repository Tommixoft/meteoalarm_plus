"""Config, reconfigure and options flows for MeteoAlarm Plus."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .alerts import collect_languages, collect_regions
from .api import MeteoAlarmClient, MeteoAlarmCountryNotFound, MeteoAlarmError
from .const import (
    AWARENESS_TYPES,
    CONF_COUNTRY,
    CONF_IGNORE_UPCOMING,
    CONF_IGNORED_TYPES,
    CONF_LANGUAGE,
    CONF_MIN_LEVEL,
    CONF_REGIONS,
    CONF_SCAN_INTERVAL,
    COUNTRIES,
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_LEVEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EMMA_ID_PATTERN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    SELECTABLE_MIN_LEVELS,
)


def _entry_unique_id(country: str, regions: list[str]) -> str:
    return f"{country}_{'_'.join(sorted(regions))}"


def _entry_title(country: str, regions: list[str], region_names: dict[str, str]) -> str:
    names = [region_names.get(region, region) for region in sorted(regions)]
    return f"MeteoAlarm {country.replace('-', ' ').title()} ({', '.join(names)})"


def _normalise_regions(raw_regions: list[str]) -> list[str] | None:
    """Upper-case and de-duplicate region IDs; None when any of them is not a valid EMMA_ID."""
    regions = sorted({region.strip().upper() for region in raw_regions})
    if not regions or not all(re.fullmatch(EMMA_ID_PATTERN, region) for region in regions):
        return None
    return regions


class MeteoAlarmPlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Choose a country, then the regions and language to follow."""

    VERSION = 1

    def __init__(self) -> None:
        self._country: str = ""
        self._region_names: dict[str, str] = {}
        self._languages: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MeteoAlarmPlusOptionsFlow:
        return MeteoAlarmPlusOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_step_country("user", user_input, default_country=None)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        current_country = self._get_reconfigure_entry().data[CONF_COUNTRY]
        return await self._async_step_country("reconfigure", user_input, current_country)

    async def _async_step_country(
        self, step_id: str, user_input: dict[str, Any] | None, default_country: str | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._country = user_input[CONF_COUNTRY]
            client = MeteoAlarmClient(async_get_clientsession(self.hass))
            try:
                payload = await client.async_get_warnings(self._country)
            except MeteoAlarmCountryNotFound:
                errors[CONF_COUNTRY] = "unknown_country"
            except MeteoAlarmError:
                errors["base"] = "cannot_connect"
            else:
                self._region_names = collect_regions(payload, DEFAULT_LANGUAGE)
                self._languages = collect_languages(payload)
                return await self.async_step_regions()

        schema = vol.Schema(
            {
                vol.Required(CONF_COUNTRY): SelectSelector(
                    SelectSelectorConfig(
                        options=list(COUNTRIES),
                        translation_key=CONF_COUNTRY,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        suggested = {CONF_COUNTRY: default_country} if default_country else {}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    async def async_step_regions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        is_reconfigure = self.source == SOURCE_RECONFIGURE
        if user_input is not None:
            regions = _normalise_regions(user_input[CONF_REGIONS])
            if regions is None:
                errors[CONF_REGIONS] = "invalid_region"
            else:
                data = {
                    CONF_COUNTRY: self._country,
                    CONF_REGIONS: regions,
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                }
                return await self._async_finish(data, is_reconfigure)

        suggested: dict[str, Any] = {CONF_LANGUAGE: DEFAULT_LANGUAGE}
        if is_reconfigure:
            entry_data = self._get_reconfigure_entry().data
            suggested = {CONF_LANGUAGE: entry_data[CONF_LANGUAGE]}
            if entry_data[CONF_COUNTRY] == self._country:
                suggested[CONF_REGIONS] = entry_data[CONF_REGIONS]
        if user_input is not None:
            suggested = user_input

        region_options = [
            SelectOptionDict(value=region_id, label=f"{region_id} – {name}")
            for region_id, name in self._region_names.items()
        ]
        language_options = sorted({DEFAULT_LANGUAGE, *self._languages})
        schema = vol.Schema(
            {
                vol.Required(CONF_REGIONS): SelectSelector(
                    SelectSelectorConfig(
                        options=region_options,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_LANGUAGE): SelectSelector(
                    SelectSelectorConfig(
                        options=language_options,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="regions",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders={"map_url": "https://meteoalarm.org"},
        )

    async def _async_finish(self, data: dict[str, Any], is_reconfigure: bool) -> ConfigFlowResult:
        unique_id = _entry_unique_id(data[CONF_COUNTRY], data[CONF_REGIONS])
        title = _entry_title(data[CONF_COUNTRY], data[CONF_REGIONS], self._region_names)
        await self.async_set_unique_id(unique_id)

        if not is_reconfigure:
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=title, data=data)

        entry = self._get_reconfigure_entry()
        duplicate = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
        if duplicate is not None and duplicate.entry_id != entry.entry_id:
            return self.async_abort(reason="already_configured")
        return self.async_update_reload_and_abort(
            entry, unique_id=unique_id, title=title, data=data
        )


class MeteoAlarmPlusOptionsFlow(OptionsFlowWithReload):
    """Filters deciding which alerts matter, and the polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        suggested = {
            CONF_MIN_LEVEL: options.get(CONF_MIN_LEVEL, DEFAULT_MIN_LEVEL),
            CONF_IGNORED_TYPES: options.get(CONF_IGNORED_TYPES, []),
            CONF_IGNORE_UPCOMING: options.get(CONF_IGNORE_UPCOMING, False),
            CONF_SCAN_INTERVAL: options.get(
                CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60)
            ),
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_MIN_LEVEL): SelectSelector(
                    SelectSelectorConfig(
                        options=list(SELECTABLE_MIN_LEVELS),
                        translation_key=CONF_MIN_LEVEL,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(CONF_IGNORED_TYPES): SelectSelector(
                    SelectSelectorConfig(
                        options=list(AWARENESS_TYPES.values()),
                        translation_key="awareness_type",
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_IGNORE_UPCOMING): BooleanSelector(),
                vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=1,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=self.add_suggested_values_to_schema(schema, suggested)
        )
