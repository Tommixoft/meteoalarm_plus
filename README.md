# MeteoAlarm Plus

Home Assistant integration for [MeteoAlarm](https://meteoalarm.org) weather warnings, with filtering.

The built-in `meteoalarm` integration reports only the first warning it finds and cannot filter.
MeteoAlarm Plus reads every warning for your regions and lets you choose which ones matter:
a **minimum awareness level** and a **list of alert types to ignore**.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/Tommixoft/meteoalarm_plus`, category *Integration*.
2. Install **MeteoAlarm Plus** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → MeteoAlarm Plus*.

Requires Home Assistant 2026.6 or newer.

## Configuration

### Setup (country, regions, language)

| Field | Description |
|---|---|
| Country | One of the countries listed below. |
| Regions | One or more EMMA_ID region codes. Regions currently in the feed are offered in the list; any other can be typed. |
| Language | Language of alert texts (e.g. `lt-LT`, `en-GB`). Falls back to the same language without region, then English. |

Change these later with *Reconfigure* on the integration entry. Several entries can be added, e.g. one per region group.

**Finding a region code (EMMA_ID).** Open [meteoalarm.org](https://meteoalarm.org), click your region on the map;
the address bar shows `geocode=EMMA_ID:LT010` → the code is `LT010`. Format: two capital letters + three digits.

Lithuania:

| Code | Region | Code | Region |
|---|---|---|---|
| LT001 | Alytus county | LT006 | Šiauliai county |
| LT002 | Kaunas county | LT007 | Tauragė county |
| LT003 | Klaipėda county | LT008 | Telšiai county |
| LT004 | Marijampolė county | LT009 | Utena county |
| LT005 | Panevėžys county | LT010 | Vilnius county |
| LT801 | South Eastern Baltic, Curonian Lagoon | | |

### Filters (*Configure* on the integration entry)

| Option | Key | Values | Default |
|---|---|---|---|
| Minimum awareness level | `min_level` | `yellow`, `orange`, `red` | `yellow` |
| Ignored alert types | `ignored_types` | list of types below | none |
| Ignore alerts that have not started yet | `ignore_upcoming` | `true` / `false` | `false` |
| Update interval (minutes) | `scan_interval` | 5 – 120 | 10 |

**Awareness levels** (MeteoAlarm's common scale across all countries):

| Value | Meaning |
|---|---|
| `yellow` | Potentially dangerous — be aware |
| `orange` | Dangerous — be prepared |
| `red` | Very dangerous — take action |

Alerts below `min_level` are ignored. Green ("no particular awareness") is never reported;
MeteoAlarm uses green updates to announce that a warning is over.

**Alert types** for `ignored_types`:

| Value | MeteoAlarm code | Type |
|---|---|---|
| `wind` | 1 | Wind |
| `snow_ice` | 2 | Snow / ice |
| `thunderstorm` | 3 | Thunderstorm |
| `fog` | 4 | Fog |
| `high_temperature` | 5 | High temperature |
| `low_temperature` | 6 | Low temperature |
| `coastal_event` | 7 | Coastal event |
| `forest_fire` | 8 | Forest fire |
| `avalanches` | 9 | Avalanches |
| `rain` | 10 | Rain |
| `flooding` | 12 | Flooding |
| `rain_flood` | 13 | Rain / flood |

Alerts with a code not in this list are always reported (their `alert_type` attribute shows the numeric code).

**Countries:** austria, belgium, bosnia-herzegovina, bulgaria, croatia, cyprus, czechia, denmark, estonia,
finland, france, germany, greece, hungary, iceland, ireland, israel, italy, latvia, lithuania, luxembourg,
malta, moldova, montenegro, netherlands, norway, poland, portugal, republic-of-north-macedonia, romania,
serbia, slovakia, slovenia, spain, sweden, switzerland, ukraine, united-kingdom.

## Entities

One device per entry, with:

| Entity | State | Attributes |
|---|---|---|
| `binary_sensor.<name>_alert` | `on` while at least one alert passes the filters | Most dangerous alert, see [alert attributes](#alert-attributes) |
| `sensor.<name>_highest_awareness_level` | `none`, `yellow`, `orange`, `red` | — |
| `sensor.<name>_alert_count` | number of alerts | `alerts`: all alerts, most dangerous first (summary fields below) |
| `event.<name>_alert_change` | time of last change | `event_type`: `alert_issued`, `alert_updated`, `alert_ended`, plus the alert's summary fields |

States change exactly at an alert's onset or expiry, not only on the next download.

### Alert attributes

Summary fields (binary sensor, `alerts` list items, change events):

| Attribute | Example | Notes |
|---|---|---|
| `level` | `yellow` | Same values as `min_level` and the highest-level sensor |
| `alert_type` | `fog` | Same values as `ignored_types`; numeric code for unknown types |
| `awareness_level` | `2; yellow; Moderate` | Core `meteoalarm` format, read by Lovelace cards |
| `awareness_type` | `4; Fog` | Core `meteoalarm` format, read by Lovelace cards |
| `event`, `headline`, `severity` | `Dangerous fog`, …, `Moderate` | In the configured language |
| `onset`, `expires` | ISO timestamps | |
| `identifier`, `regions` | | MeteoAlarm alert ID, EMMA_IDs it covers |

The binary sensor adds `description`, `instruction`, `urgency`, `certainty`, `effective`, `area`,
`senderName`, `language` and `web`.

### Lovelace cards

The binary sensor uses the same attributes as the built-in `meteoalarm` integration, so cards made
for it work unchanged. They show the most dangerous alert that passes your filters:

- [MeteoalarmCard](https://github.com/MrBartusek/MeteoalarmCard) with `integration: meteoalarm`
- [Weather Alerts Card](https://github.com/seevee/weather_alerts_card), detected automatically

```yaml
type: custom:meteoalarm-card
integration: meteoalarm
entities: binary_sensor.meteoalarm_lithuania_vilnius_county_alert
```

```yaml
type: custom:weather-alerts-card
entity: binary_sensor.meteoalarm_lithuania_vilnius_county_alert
colorTheme: meteoalarm
```

### Notification example

```yaml
triggers:
  - trigger: state
    entity_id: event.meteoalarm_lithuania_vilnius_county_alert_change
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.event_type in ['alert_issued', 'alert_updated'] }}"
actions:
  - action: notify.notify
    data:
      title: "{{ trigger.to_state.attributes.headline }}"
      message: >
        {{ trigger.to_state.attributes.level | title }}:
        {{ trigger.to_state.attributes.onset | as_datetime | as_local }} –
        {{ trigger.to_state.attributes.expires | as_datetime | as_local }}
```

## Data

Warnings come from `https://feeds.meteoalarm.org/api/v1/warnings/feeds-<country>`.
Information provided by MeteoAlarm, licensed under terms equivalent to CC BY 4.0.

## Development

Tests need Linux (Home Assistant does not run on Windows):

```sh
docker run --rm -v "$PWD:/app" -w /app python:3.14 sh -c \
  "pip install -r requirements_test.txt && pytest"
```

## License

[MIT](LICENSE)
