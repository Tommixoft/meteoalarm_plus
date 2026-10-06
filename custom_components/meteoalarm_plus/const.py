"""Constants for the MeteoAlarm Plus integration."""

from datetime import timedelta
from enum import IntEnum, StrEnum

DOMAIN = "meteoalarm_plus"
ATTRIBUTION = "Information provided by MeteoAlarm"

API_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-{country}"

CONF_COUNTRY = "country"
CONF_REGIONS = "regions"
CONF_LANGUAGE = "language"
CONF_MIN_LEVEL = "min_level"
CONF_IGNORED_TYPES = "ignored_types"
CONF_IGNORE_UPCOMING = "ignore_upcoming"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_LANGUAGE = "en-GB"
DEFAULT_MIN_LEVEL = "yellow"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 120

EMMA_ID_PATTERN = r"^[A-Z]{2}\d{3}$"

COUNTRIES = (
    "austria",
    "belgium",
    "bosnia-herzegovina",
    "bulgaria",
    "croatia",
    "cyprus",
    "czechia",
    "denmark",
    "estonia",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "iceland",
    "ireland",
    "israel",
    "italy",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "moldova",
    "montenegro",
    "netherlands",
    "norway",
    "poland",
    "portugal",
    "republic-of-north-macedonia",
    "romania",
    "serbia",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
    "switzerland",
    "ukraine",
    "united-kingdom",
)


class AwarenessLevel(IntEnum):
    """MeteoAlarm awareness level, the normalised cross-country danger scale."""

    GREEN = 1
    YELLOW = 2
    ORANGE = 3
    RED = 4

    @property
    def slug(self) -> str:
        return self.name.lower()

    @classmethod
    def from_slug(cls, slug: str) -> AwarenessLevel:
        return cls[slug.upper()]


# Levels a user can choose as the minimum; green means "no danger" and is never reported.
SELECTABLE_MIN_LEVELS = ("yellow", "orange", "red")

# Codes from the MeteoAlarm awareness_type parameter ("<code>; <name>").
# Code 11 is reserved and unused by MeteoAlarm.
AWARENESS_TYPES: dict[int, str] = {
    1: "wind",
    2: "snow_ice",
    3: "thunderstorm",
    4: "fog",
    5: "high_temperature",
    6: "low_temperature",
    7: "coastal_event",
    8: "forest_fire",
    9: "avalanches",
    10: "rain",
    12: "flooding",
    13: "rain_flood",
}


class AlertChange(StrEnum):
    """Event types fired when the set of relevant alerts changes."""

    ISSUED = "alert_issued"
    UPDATED = "alert_updated"
    ENDED = "alert_ended"
