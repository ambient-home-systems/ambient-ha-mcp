"""Complementary state and registry data for discovery tests."""

from typing import Any

from ambient_ha.ha.websocket import RegistrySnapshot

STATES: list[dict[str, Any]] = [
    {
        "entity_id": "light.kitchen_ceiling",
        "state": "on",
        "attributes": {
            "friendly_name": "Kitchen Ceiling",
            "brightness": 180,
            "entity_picture": "http://private.local/kitchen.jpg",
            "access_token": "must-not-escape",
        },
        "last_changed": "2026-08-25T12:00:00+00:00",
        "last_updated": "2026-08-25T12:00:05+00:00",
    },
    {
        "entity_id": "light.garage_overhead_lights",
        "state": "off",
        "attributes": {"friendly_name": "Garage Overhead Lights", "brightness": 0},
        "last_changed": "2026-08-25T11:00:00+00:00",
        "last_updated": "2026-08-25T11:00:00+00:00",
    },
    {
        "entity_id": "cover.garage_door",
        "state": "open",
        "attributes": {"friendly_name": "Garage Door", "current_position": 100},
        "last_changed": "2026-08-25T12:10:00+00:00",
        "last_updated": "2026-08-25T12:10:00+00:00",
    },
    {
        "entity_id": "binary_sensor.basement_motion",
        "state": "unavailable",
        "attributes": {"friendly_name": "Basement Motion", "device_class": "motion"},
        "last_changed": "2026-08-25T10:00:00+00:00",
        "last_updated": "2026-08-25T10:00:00+00:00",
    },
    {
        "entity_id": "sensor.primary_bedroom_temperature",
        "state": "72.1",
        "attributes": {
            "friendly_name": "Primary Bedroom Temperature",
            "device_class": "temperature",
            "unit_of_measurement": "°F",
        },
        "last_changed": "2026-08-25T12:00:00+00:00",
        "last_updated": "2026-08-25T12:15:00+00:00",
    },
    {
        "entity_id": "sensor.garage_temperature",
        "state": "51.2",
        "attributes": {
            "friendly_name": "Garage Temperature",
            "device_class": "temperature",
            "unit_of_measurement": "°F",
        },
        "last_changed": "2026-08-25T12:00:00+00:00",
        "last_updated": "2026-08-25T12:15:00+00:00",
    },
    {
        "entity_id": "sensor.garage_humidity",
        "state": "unknown",
        "attributes": {
            "friendly_name": "Garage Humidity",
            "device_class": "humidity",
            "unit_of_measurement": "%",
        },
        "last_changed": "2026-08-25T12:00:00+00:00",
        "last_updated": "2026-08-25T12:15:00+00:00",
    },
    {
        "entity_id": "camera.front_door",
        "state": "streaming",
        "attributes": {
            "friendly_name": "Front Door Camera",
            "entity_picture": "/api/camera_proxy/camera.front_door?token=private",
            "stream_source": "rtsp://user:password@private.local/stream",
            "access_token": "camera-secret",
            "supported_features": 2,
        },
        "last_changed": "2026-08-25T12:00:00+00:00",
        "last_updated": "2026-08-25T12:15:00+00:00",
    },
]

REGISTRIES = RegistrySnapshot(
    entities=(
        {"entity_id": "light.kitchen_ceiling", "device_id": "device_kitchen_light"},
        {"entity_id": "light.garage_overhead_lights", "device_id": "device_garage"},
        {"entity_id": "cover.garage_door", "device_id": "device_garage"},
        {"entity_id": "binary_sensor.basement_motion", "device_id": "device_basement"},
        {
            "entity_id": "sensor.primary_bedroom_temperature",
            "device_id": "device_bedroom",
        },
        {
            "entity_id": "sensor.garage_temperature",
            "device_id": "device_garage",
            "area_id": "kitchen",
        },
        {"entity_id": "sensor.garage_humidity", "device_id": "device_garage"},
        {"entity_id": "camera.front_door", "area_id": "garage"},
    ),
    devices=(
        {"id": "device_kitchen_light", "name": "Kitchen Light", "area_id": "kitchen"},
        {"id": "device_garage", "name_by_user": "Garage Controller", "area_id": "garage"},
        {"id": "device_basement", "name": "Basement Motion Detector", "area_id": "basement"},
        {"id": "device_bedroom", "name": "Bedroom Climate", "area_id": "primary_bedroom"},
    ),
    areas=(
        {"area_id": "kitchen", "name": "Kitchen", "floor_id": "ground_floor"},
        {"area_id": "garage", "name": "Garage", "floor_id": "ground_floor"},
        {"area_id": "basement", "name": "Basement", "floor_id": "lower_level"},
        {
            "area_id": "primary_bedroom",
            "name": "Primary Bedroom",
            "floor_id": "upstairs",
        },
    ),
    floors=(
        {"floor_id": "lower_level", "name": "Lower Level", "level": -1},
        {"floor_id": "ground_floor", "name": "Ground Floor", "level": 0},
        {"floor_id": "upstairs", "name": "Upstairs", "level": 1},
    ),
)
