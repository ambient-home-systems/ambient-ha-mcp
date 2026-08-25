from ambient_ha.ha.discovery import DiscoveryResolver, sanitize_attributes
from ambient_ha.models.discovery import EntitySearchFilters
from tests.fixtures.discovery import REGISTRIES, STATES


def test_entity_join_uses_entity_area_before_device_area() -> None:
    resolver = DiscoveryResolver(REGISTRIES)

    inherited = resolver.entity(STATES[1])
    overridden = resolver.entity(STATES[5])

    assert (inherited.area_id, inherited.area_name, inherited.floor_name) == (
        "garage",
        "Garage",
        "Ground Floor",
    )
    assert overridden.device_name == "Garage Controller"
    assert (overridden.area_id, overridden.area_name, overridden.floor_name) == (
        "kitchen",
        "Kitchen",
        "Ground Floor",
    )


def test_entity_attributes_are_allowlisted_bounded_and_secret_free() -> None:
    resolver = DiscoveryResolver(REGISTRIES)

    light = resolver.entity(STATES[0])
    camera = resolver.entity(STATES[-1])

    assert light.attributes == {"brightness": 180}
    assert camera.attributes == {"supported_features": 2}
    rendered = f"{light.model_dump_json()} {camera.model_dump_json()}"
    assert "must-not-escape" not in rendered
    assert "rtsp://" not in rendered
    assert "camera_proxy" not in rendered


def test_attribute_sanitizer_caps_strings_collections_and_count() -> None:
    attributes = {f"reading_{index}_temperature": index for index in range(50)}
    attributes["temperature"] = "x" * 400
    attributes["hvac_modes"] = [str(index) for index in range(30)]

    result = sanitize_attributes(attributes)

    assert len(result) == 40
    assert all(len(value) <= 20 for value in result.values() if isinstance(value, list))

    nested = sanitize_attributes(
        {
            "hvac_modes": {
                "safe": "heat",
                "access_token": "nested-secret",
                "endpoint": "https://private.example",
            }
        }
    )
    assert nested == {"hvac_modes": {"safe": "heat"}}


def test_search_matches_names_ids_and_composable_filters() -> None:
    resolver = DiscoveryResolver(REGISTRIES)

    ranked = resolver.search(STATES, EntitySearchFilters(query="garage light"))
    filtered = resolver.search(
        STATES,
        EntitySearchFilters(
            domain="sensor",
            area="Garage",
            floor="ground_floor",
            available=True,
        ),
    )
    unavailable = resolver.search(STATES, EntitySearchFilters(available=False))

    assert ranked.entities[0].entity_id == "light.garage_overhead_lights"
    assert [entity.entity_id for entity in filtered.entities] == ["sensor.garage_humidity"]
    assert [entity.entity_id for entity in unavailable.entities] == [
        "binary_sensor.basement_motion"
    ]


def test_search_is_deterministic_and_reports_truncation() -> None:
    page = DiscoveryResolver(REGISTRIES).search(
        STATES, EntitySearchFilters(query="garage", limit=2)
    )

    assert page.total_matches == 5
    assert page.returned == 2
    assert page.truncated is True
    assert [entity.entity_id for entity in page.entities] == [
        "cover.garage_door",
        "sensor.garage_humidity",
    ]


def test_area_floor_and_domain_aggregates_are_compact() -> None:
    resolver = DiscoveryResolver(REGISTRIES)

    garage = resolver.get_area(STATES, "Garage", include_entities=True, limit=2)
    floor = resolver.get_floor(STATES, "ground floor")
    sensors = resolver.domain_summary(STATES, "sensor")

    assert garage is not None
    assert garage.entity_count == 4
    assert garage.entity_counts_by_domain == {"camera": 1, "cover": 1, "light": 1, "sensor": 1}
    assert len(garage.entities) == 2
    assert garage.entities_truncated is True
    assert floor is not None
    assert floor.area_count == 2
    assert floor.entity_count == 6
    assert floor.entity_counts_by_domain == {
        "camera": 1,
        "cover": 1,
        "light": 2,
        "sensor": 2,
    }
    assert sensors.model_dump() == {
        "domain": "sensor",
        "total": 3,
        "available": 3,
        "unavailable": 0,
        "unknown": 1,
        "states": {"51.2": 1, "72.1": 1, "unknown": 1},
    }


def test_missing_area_and_floor_return_none() -> None:
    resolver = DiscoveryResolver(REGISTRIES)

    assert resolver.get_area(STATES, "attic", include_entities=False, limit=25) is None
    assert resolver.get_floor(STATES, "attic") is None
