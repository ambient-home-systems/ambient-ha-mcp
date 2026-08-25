from datetime import UTC, datetime

from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.home import HomeAnalyzer
from ambient_ha.models.home import (
    LocationFilters,
    LowBatteryFilters,
    OpeningFilters,
    UnavailableEntityFilters,
)
from tests.fixtures.home import HOME_REGISTRIES, HOME_STATES


def make_analyzer(*, ignored: frozenset[str] = frozenset()) -> HomeAnalyzer:
    entities = DiscoveryResolver(HOME_REGISTRIES).entities(HOME_STATES, include_attributes=True)
    return HomeAnalyzer(
        entities,
        battery_warning_threshold=20,
        ignored_entity_ids=ignored,
        now=datetime(2026, 8, 25, 12, tzinfo=UTC),
    )


def test_openings_prioritize_device_class_and_use_conservative_fallbacks() -> None:
    page = make_analyzer().openings(OpeningFilters(state="any", limit=20))

    assert [
        (entity.entity_id, entity.opening_type, entity.normalized_state) for entity in page.entities
    ] == [
        ("binary_sensor.basement_hatch", "opening", "open"),
        ("binary_sensor.front_door", "door", "open"),
        ("binary_sensor.kitchen_window", "window", "closed"),
        ("binary_sensor.patio_door", "door", "open"),
        ("cover.garage_door", "garage_door", "open"),
    ]
    assert "binary_sensor.doorbell_motion" not in {entity.entity_id for entity in page.entities}
    garage = make_analyzer().openings(
        OpeningFilters(area="Garage", opening_type="garage_door", state="open")
    )
    assert [entity.entity_id for entity in garage.entities] == ["cover.garage_door"]


def test_low_batteries_require_sensor_device_class_unit_and_numeric_percentage() -> None:
    page = make_analyzer().low_batteries(LowBatteryFilters(threshold=20, limit=20))

    assert [(entity.entity_id, entity.battery_percent) for entity in page.entities] == [
        ("sensor.front_lock_battery", 15.0)
    ]
    serialized = page.model_dump_json()
    assert "charging" not in serialized
    assert "voltage" not in serialized
    assert "binary_sensor.remote_battery" not in serialized
    assert "sensor.named_battery" not in serialized


def test_unavailable_duration_is_factual_and_missing_evidence_is_explicit() -> None:
    analyzer = make_analyzer()
    page = analyzer.unavailable_entities(
        UnavailableEntityFilters(minimum_duration_minutes=120, limit=10)
    )
    missing_state = dict(
        next(state for state in HOME_STATES if state["entity_id"] == "sensor.offline_bridge")
    )
    missing_state.pop("last_changed")
    missing_analyzer = HomeAnalyzer(
        DiscoveryResolver(HOME_REGISTRIES).entities([missing_state], include_attributes=True),
        battery_warning_threshold=20,
        now=datetime(2026, 8, 25, 12, tzinfo=UTC),
    )
    incomplete = missing_analyzer.unavailable_entities(
        UnavailableEntityFilters(minimum_duration_minutes=120)
    )

    assert page.entities[0].unavailable_duration_seconds == 10800
    assert page.duration_filter_complete is True
    assert incomplete.entities == []
    assert incomplete.duration_filter_complete is False
    assert incomplete.entities_without_duration_evidence == 1


def test_lights_location_and_limits_are_compact() -> None:
    page = make_analyzer().lights_on(LocationFilters(floor="Ground Floor", limit=1))

    assert page.returned == 1
    assert page.entities[0].entity_id == "light.kitchen"
    assert page.entities[0].brightness == 128
    assert "attributes" not in page.model_dump_json()


def test_diagnostics_have_exact_categories_severity_and_sensor_state_language() -> None:
    report = make_analyzer().diagnose(limit=100)
    by_category = {finding.category: finding for finding in report.findings}

    assert by_category["smoke_detected"].severity == "critical"
    assert "Home Assistant reports smoke sensor" in by_category["smoke_detected"].message
    assert by_category["carbon_monoxide_detected"].severity == "critical"
    assert "carbon monoxide sensor" in by_category["carbon_monoxide_detected"].message
    assert by_category["moisture_detected"].severity == "warning"
    assert by_category["connectivity_problem"].entity.state == "off"
    assert by_category["open_garage"].severity == "warning"
    assert by_category["open_door"].severity == "info"
    assert report.severity_counts == {"critical": 2, "warning": 6, "info": 4}
    assert "fire" not in report.model_dump_json().casefold()


def test_home_summary_includes_only_supported_sections_and_never_tracker_coordinates() -> None:
    summary = make_analyzer().home_summary(detail_limit=2)
    names = [section.name for section in summary.sections]

    assert names == [
        "occupancy",
        "openings",
        "lighting",
        "climate",
        "environment",
        "device_health",
        "safety",
        "energy",
    ]
    assert summary.total_entities == len(HOME_STATES)
    assert summary.attention_items_truncated is True
    serialized = summary.model_dump_json()
    assert "latitude" not in serialized
    assert "longitude" not in serialized
    assert "39.123" not in serialized


def test_missing_domains_produce_no_fabricated_sections_and_ignored_entities_stay_out() -> None:
    empty = HomeAnalyzer([], battery_warning_threshold=20).home_summary()
    ignored = make_analyzer(ignored=frozenset({"binary_sensor.hall_smoke"})).diagnose(limit=100)

    assert empty.sections == []
    assert empty.attention_items == []
    assert "binary_sensor.hall_smoke" not in ignored.model_dump_json()


def test_large_diagnostic_result_is_deterministically_limited_and_compact() -> None:
    states = [
        {
            "entity_id": f"sensor.offline_{index:03d}",
            "state": "unavailable",
            "attributes": {"friendly_name": f"Offline {index}"},
            "last_changed": "2026-08-25T10:00:00+00:00",
        }
        for index in range(250)
    ]
    entities = DiscoveryResolver(HOME_REGISTRIES).entities(states, include_attributes=True)
    report = HomeAnalyzer(
        entities,
        battery_warning_threshold=20,
        now=datetime(2026, 8, 25, 12, tzinfo=UTC),
    ).diagnose(limit=100)

    assert report.total_findings == 250
    assert report.returned == 100
    assert report.truncated is True
    assert len(report.model_dump_json()) < 50000
