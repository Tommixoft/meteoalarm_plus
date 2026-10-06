"""Parsing and filtering of MeteoAlarm warnings.

Kept free of Home Assistant imports so the alert logic is testable on its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from .const import AWARENESS_TYPES, AlertChange, AwarenessLevel

_LOGGER = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "en"


@dataclass(frozen=True, slots=True)
class Alert:
    """One MeteoAlarm warning, reduced to a single language."""

    identifier: str
    msg_type: str
    sent: datetime
    references: frozenset[str]
    language: str
    event: str
    headline: str
    description: str
    instruction: str
    severity: str
    urgency: str
    certainty: str
    level: AwarenessLevel
    type_code: int
    type_slug: str | None
    type_name: str
    onset: datetime
    expires: datetime
    areas: tuple[tuple[str, str], ...]
    sender_name: str
    web: str

    @property
    def region_ids(self) -> frozenset[str]:
        return frozenset(region_id for region_id, _ in self.areas)

    def is_started(self, now: datetime) -> bool:
        return self.onset <= now

    def is_expired(self, now: datetime) -> bool:
        return self.expires <= now


@dataclass(frozen=True, slots=True)
class AlertFilter:
    """User preferences deciding which alerts are relevant."""

    regions: frozenset[str]
    min_level: AwarenessLevel
    ignored_types: frozenset[str]
    ignore_upcoming: bool

    def is_relevant(self, alert: Alert) -> bool:
        return (
            alert.msg_type != "Cancel"
            and alert.level >= max(self.min_level, AwarenessLevel.YELLOW)
            and alert.type_slug not in self.ignored_types
            and not alert.region_ids.isdisjoint(self.regions)
        )

    def is_active(self, alert: Alert, now: datetime) -> bool:
        if alert.is_expired(now):
            return False
        return alert.is_started(now) or not self.ignore_upcoming


def parse_warnings(payload: Mapping[str, Any], language: str) -> list[Alert]:
    """Parse the JSON feed into alerts, dropping public-irrelevant and superseded ones.

    A warning is superseded when a newer one in the feed references it (CAP Update/Cancel);
    only the newest version of each warning chain is kept. References are read from the raw
    warnings, because a Cancel often lacks the fields needed to parse it as an alert.
    """
    alerts: list[Alert] = []
    superseded: set[str] = set()
    for warning in payload.get("warnings", []):
        try:
            raw = warning["alert"]
            if raw.get("status") == "Actual":
                superseded |= _parse_references(raw.get("references", ""))
            alert = _parse_alert(raw, language)
        except (KeyError, TypeError, ValueError, IndexError) as err:
            _LOGGER.debug("Skipping malformed warning %s: %r", warning.get("uuid"), err)
            continue
        if alert is not None:
            alerts.append(alert)

    return [alert for alert in alerts if alert.identifier not in superseded]


def select_alerts(alerts: Iterable[Alert], alert_filter: AlertFilter, now: datetime) -> list[Alert]:
    """Return relevant, currently active alerts, most dangerous and soonest first."""
    selected = [
        alert
        for alert in alerts
        if alert_filter.is_relevant(alert) and alert_filter.is_active(alert, now)
    ]
    return sorted(selected, key=lambda alert: (-alert.level, alert.onset, alert.identifier))


def next_transition(
    alerts: Iterable[Alert], alert_filter: AlertFilter, now: datetime
) -> datetime | None:
    """Return the next moment an alert starts or expires, so state can change on time.

    Onsets only matter when upcoming alerts are hidden; otherwise they are already shown.
    """
    moments = [
        moment
        for alert in alerts
        if alert_filter.is_relevant(alert)
        for moment in (
            (alert.onset, alert.expires) if alert_filter.ignore_upcoming else (alert.expires,)
        )
        if moment > now
    ]
    return min(moments, default=None)


def diff_alerts(
    previous: Iterable[Alert], current: Iterable[Alert]
) -> list[tuple[AlertChange, Alert]]:
    """Describe how the active alert set changed between two snapshots.

    An alert that references a previously active alert is reported as an update of it;
    previously active alerts that vanished without being replaced are reported as ended.
    """
    previous_by_id = {alert.identifier: alert for alert in previous}
    current_list = list(current)
    current_ids = {alert.identifier for alert in current_list}

    changes: list[tuple[AlertChange, Alert]] = []
    replaced_ids: set[str] = set()
    for alert in current_list:
        if alert.identifier in previous_by_id:
            continue
        replaced = alert.references & previous_by_id.keys()
        if replaced:
            replaced_ids |= replaced
            changes.append((AlertChange.UPDATED, alert))
        else:
            changes.append((AlertChange.ISSUED, alert))

    for identifier, alert in previous_by_id.items():
        if identifier not in current_ids and identifier not in replaced_ids:
            changes.append((AlertChange.ENDED, alert))
    return changes


def collect_regions(payload: Mapping[str, Any], language: str) -> dict[str, str]:
    """Map every EMMA_ID mentioned in the feed to its area name, sorted by ID."""
    regions: dict[str, str] = {}
    for warning in payload.get("warnings", []):
        try:
            info = _pick_info(warning["alert"]["info"], language)
            regions.update(_parse_areas(info.get("area", [])))
        except KeyError, TypeError, IndexError:
            continue
    return dict(sorted(regions.items()))


def collect_languages(payload: Mapping[str, Any]) -> list[str]:
    """Return the language tags the feed's warnings are published in."""
    languages: set[str] = set()
    for warning in payload.get("warnings", []):
        try:
            languages.update(info["language"] for info in warning["alert"]["info"])
        except KeyError, TypeError:
            continue
    return sorted(languages)


def _parse_alert(raw: Mapping[str, Any], language: str) -> Alert | None:
    if raw.get("status") != "Actual" or raw.get("scope") != "Public":
        return None

    info = _pick_info(raw["info"], language)
    parameters = {p["valueName"]: p["value"] for p in info.get("parameter", [])}
    level_code = int(parameters["awareness_level"].split(";")[0])
    type_code_text, _, type_name = parameters["awareness_type"].partition(";")
    type_code = int(type_code_text)

    return Alert(
        identifier=raw["identifier"],
        msg_type=raw["msgType"],
        sent=_parse_datetime(raw["sent"]),
        references=_parse_references(raw.get("references", "")),
        language=info["language"],
        event=info["event"],
        headline=info.get("headline", ""),
        description=info.get("description", ""),
        instruction=info.get("instruction", ""),
        severity=info["severity"],
        urgency=info["urgency"],
        certainty=info["certainty"],
        level=AwarenessLevel(level_code),
        type_code=type_code,
        type_slug=AWARENESS_TYPES.get(type_code),
        type_name=type_name.strip(),
        onset=_parse_datetime(info.get("onset") or info.get("effective") or raw["sent"]),
        expires=_parse_datetime(info["expires"]),
        areas=_parse_areas(info.get("area", [])),
        sender_name=info.get("senderName", ""),
        web=info.get("web", ""),
    )


def _pick_info(infos: list[Mapping[str, Any]], language: str) -> Mapping[str, Any]:
    """Pick the info block for the language: exact tag, then same primary language, then English."""
    wanted = language.lower()
    by_language = {info["language"].lower(): info for info in infos}
    if wanted in by_language:
        return by_language[wanted]

    for primary in (wanted.split("-")[0], FALLBACK_LANGUAGE):
        for tag, info in by_language.items():
            if tag.split("-")[0] == primary:
                return info
    return infos[0]


def _parse_references(references: str) -> frozenset[str]:
    """Extract identifiers from CAP references: space-separated 'sender,identifier,sent' triples."""
    identifiers = set()
    for triple in references.split():
        parts = triple.split(",")
        if len(parts) >= 2:
            identifiers.add(parts[1])
    return frozenset(identifiers)


def _parse_areas(areas: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, str], ...]:
    parsed = []
    for area in areas:
        for geocode in area.get("geocode", []):
            if geocode.get("valueName") == "EMMA_ID":
                parsed.append((geocode["value"], area.get("areaDesc", "")))
    return tuple(parsed)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
