"""Tests for alert parsing and filtering."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.meteoalarm_plus.alerts import (
    AlertFilter,
    diff_alerts,
    next_transition,
    parse_warnings,
    select_alerts,
)
from custom_components.meteoalarm_plus.const import AlertChange, AwarenessLevel

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
LEVEL_NAMES = {1: "green; Minor", 2: "yellow; Moderate", 3: "orange; Severe", 4: "red; Extreme"}
TYPE_NAMES = {1: "Wind", 3: "Thunderstorm", 4: "Fog", 10: "Rain", 11: "Unknown"}


def make_warning(
    identifier: str,
    *,
    level: int = 2,
    type_code: int = 4,
    onset: datetime = NOW - timedelta(hours=1),
    expires: datetime = NOW + timedelta(hours=6),
    regions: tuple[str, ...] = ("LT010",),
    msg_type: str = "Alert",
    references: str = "",
    status: str = "Actual",
) -> dict[str, Any]:
    def info(language: str, event: str, area_suffix: str) -> dict[str, Any]:
        return {
            "language": language,
            "event": event,
            "headline": f"{event} headline",
            "description": f"{event} description",
            "instruction": f"{event} instruction",
            "severity": "Moderate",
            "urgency": "Immediate",
            "certainty": "Likely",
            "onset": onset.isoformat(),
            "expires": expires.isoformat(),
            "senderName": "LHMS",
            "parameter": [
                {"valueName": "awareness_type", "value": f"{type_code}; {TYPE_NAMES[type_code]}"},
                {"valueName": "awareness_level", "value": f"{level}; {LEVEL_NAMES[level]}"},
            ],
            "area": [
                {
                    "areaDesc": f"{region} {area_suffix}",
                    "geocode": [{"valueName": "EMMA_ID", "value": region}],
                }
                for region in regions
            ],
        }

    return {
        "uuid": identifier,
        "alert": {
            "identifier": identifier,
            "msgType": msg_type,
            "status": status,
            "scope": "Public",
            "sender": "LHMS",
            "sent": (NOW - timedelta(hours=2)).isoformat(),
            "references": references,
            "info": [info("lt-LT", "Rūkas", "apskritis"), info("en-GB", "Dangerous fog", "county")],
        },
    }


def make_filter(**overrides: Any) -> AlertFilter:
    settings = {
        "regions": frozenset({"LT010"}),
        "min_level": AwarenessLevel.YELLOW,
        "ignored_types": frozenset(),
        "ignore_upcoming": False,
    }
    settings.update(overrides)
    return AlertFilter(**settings)


def parse(*warnings: dict[str, Any], language: str = "en-GB"):
    return parse_warnings({"warnings": list(warnings)}, language)


def test_parses_awareness_fields_from_parameters_in_any_order() -> None:
    warning = make_warning("a", level=3, type_code=1)
    warning["alert"]["info"][1]["parameter"].reverse()

    alert = parse(warning)[0]

    assert alert.level is AwarenessLevel.ORANGE
    assert alert.type_code == 1
    assert alert.type_slug == "wind"
    assert alert.type_name == "Wind"


def test_unknown_awareness_type_is_kept_without_slug() -> None:
    alert = parse(make_warning("a", type_code=11))[0]

    assert alert.type_code == 11
    assert alert.type_slug is None


@pytest.mark.parametrize(
    ("language", "expected_event"),
    [
        ("lt-LT", "Rūkas"),
        ("lt", "Rūkas"),
        ("LT-lt", "Rūkas"),
        ("en-GB", "Dangerous fog"),
        ("de", "Dangerous fog"),
    ],
)
def test_info_block_chosen_by_language_with_english_fallback(
    language: str, expected_event: str
) -> None:
    assert parse(make_warning("a"), language=language)[0].event == expected_event


def test_non_actual_warnings_are_dropped() -> None:
    assert parse(make_warning("a", status="Exercise")) == []


def test_malformed_warning_is_skipped_without_losing_others() -> None:
    broken = make_warning("broken")
    del broken["alert"]["info"][0]["parameter"][1]
    del broken["alert"]["info"][1]["parameter"][1]

    assert [alert.identifier for alert in parse(broken, make_warning("ok"))] == ["ok"]


def test_referenced_warning_is_superseded() -> None:
    original = make_warning("old")
    update = make_warning(
        "new", level=3, msg_type="Update", references="LHMS,old,2026-10-06T08:00:00+00:00"
    )

    assert [alert.identifier for alert in parse(original, update)] == ["new"]


def test_cancel_without_awareness_parameters_still_supersedes() -> None:
    cancel = make_warning(
        "cancel", msg_type="Cancel", references="LHMS,old,2026-10-06T08:00:00+00:00"
    )
    for info in cancel["alert"]["info"]:
        del info["parameter"]

    assert parse(make_warning("old"), cancel) == []


def test_green_all_clear_update_removes_the_alert_it_replaces() -> None:
    original = make_warning("old")
    all_clear = make_warning(
        "clear", level=1, msg_type="Update", references="LHMS,old,2026-10-06T08:00:00+00:00"
    )

    assert select_alerts(parse(original, all_clear), make_filter(), NOW) == []


def test_alerts_below_min_level_are_ignored() -> None:
    alerts = parse(
        make_warning("yellow", level=2),
        make_warning("orange", level=3),
        make_warning("red", level=4),
    )

    selected = select_alerts(alerts, make_filter(min_level=AwarenessLevel.ORANGE), NOW)

    assert [alert.identifier for alert in selected] == ["red", "orange"]


def test_green_is_never_reported_even_if_min_level_allows_it() -> None:
    alerts = parse(make_warning("green", level=1))

    assert select_alerts(alerts, make_filter(min_level=AwarenessLevel.GREEN), NOW) == []


def test_ignored_awareness_types_are_dropped() -> None:
    alerts = parse(make_warning("fog", type_code=4), make_warning("wind", type_code=1))

    selected = select_alerts(alerts, make_filter(ignored_types=frozenset({"fog"})), NOW)

    assert [alert.identifier for alert in selected] == ["wind"]


def test_alerts_for_other_regions_are_dropped() -> None:
    alerts = parse(
        make_warning("here", regions=("LT010", "LT009")), make_warning("there", regions=("LT001",))
    )

    assert [alert.identifier for alert in select_alerts(alerts, make_filter(), NOW)] == ["here"]


def test_expired_alerts_are_dropped() -> None:
    alerts = parse(
        make_warning("expired", onset=NOW - timedelta(days=2), expires=NOW - timedelta(days=1))
    )

    assert select_alerts(alerts, make_filter(), NOW) == []


def test_upcoming_alerts_are_kept_unless_ignored() -> None:
    alerts = parse(make_warning("upcoming", onset=NOW + timedelta(hours=3)))

    assert len(select_alerts(alerts, make_filter(), NOW)) == 1
    assert select_alerts(alerts, make_filter(ignore_upcoming=True), NOW) == []


def test_cancel_messages_are_never_active() -> None:
    alerts = parse(make_warning("cancel", msg_type="Cancel"))

    assert select_alerts(alerts, make_filter(), NOW) == []


def test_alerts_sorted_by_level_then_onset() -> None:
    alerts = parse(
        make_warning("yellow-early", level=2, onset=NOW - timedelta(hours=3)),
        make_warning("orange", level=3),
        make_warning("yellow-late", level=2, onset=NOW - timedelta(hours=1)),
    )

    selected = select_alerts(alerts, make_filter(), NOW)

    assert [alert.identifier for alert in selected] == ["orange", "yellow-early", "yellow-late"]


def test_next_transition_includes_onsets_when_upcoming_alerts_are_hidden() -> None:
    alerts = parse(
        make_warning("active", expires=NOW + timedelta(hours=5)),
        make_warning("upcoming", onset=NOW + timedelta(hours=2), expires=NOW + timedelta(hours=8)),
        make_warning("ignored", type_code=1, expires=NOW + timedelta(minutes=5)),
    )
    alert_filter = make_filter(ignored_types=frozenset({"wind"}), ignore_upcoming=True)

    assert next_transition(alerts, alert_filter, NOW) == NOW + timedelta(hours=2)


def test_next_transition_skips_onsets_when_upcoming_alerts_are_shown() -> None:
    alerts = parse(
        make_warning("active", expires=NOW + timedelta(hours=5)),
        make_warning("upcoming", onset=NOW + timedelta(hours=2), expires=NOW + timedelta(hours=8)),
    )

    assert next_transition(alerts, make_filter(), NOW) == NOW + timedelta(hours=5)


def test_next_transition_is_none_without_future_moments() -> None:
    assert next_transition([], make_filter(), NOW) is None


def test_diff_reports_issued_updated_and_ended() -> None:
    before = parse(make_warning("kept"), make_warning("replaced"), make_warning("gone"))
    after = parse(
        make_warning("kept"),
        make_warning(
            "replacement",
            level=3,
            msg_type="Update",
            references="LHMS,replaced,2026-10-06T08:00:00+00:00",
        ),
        make_warning("brand-new"),
    )

    changes = {(change, alert.identifier) for change, alert in diff_alerts(before, after)}

    assert changes == {
        (AlertChange.UPDATED, "replacement"),
        (AlertChange.ISSUED, "brand-new"),
        (AlertChange.ENDED, "gone"),
    }


def test_diff_is_empty_when_nothing_changed() -> None:
    alerts = parse(make_warning("a"))

    assert diff_alerts(alerts, alerts) == []


def test_real_lithuania_feed() -> None:
    payload = json.loads(
        Path(__file__).with_name("fixtures").joinpath("lithuania.json").read_text("utf-8")
    )
    alerts = parse_warnings(payload, "lt")
    now = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)

    selected = select_alerts(alerts, make_filter(regions=frozenset({"LT010"})), now)

    assert [(alert.type_slug, alert.level, alert.language) for alert in selected] == [
        ("fog", AwarenessLevel.YELLOW, "lt-LT")
    ]
    assert selected[0].onset == datetime(2026, 10, 6, 21, 30, tzinfo=UTC)
    assert select_alerts(alerts, make_filter(ignored_types=frozenset({"fog"})), now) == []
