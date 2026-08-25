"""Representative whole-home state and registry fixtures for deterministic diagnostics."""

from typing import Any

from ambient_ha.ha.websocket import RegistrySnapshot


def _state(
    entity_id: str,
    state: str,
    name: str,
    *,
    device_class: str | None = None,
    unit: str | None = None,
    last_changed: str | None = "2026-08-25T10:00:00+00:00",
    **attributes: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {"friendly_name": name, **attributes}
    if device_class is not None:
        values["device_class"] = device_class
    if unit is not None:
        values["unit_of_measurement"] = unit
    result: dict[str, Any] = {
        "entity_id": entity_id,
        "state": state,
        "attributes": values,
        "last_updated": "2026-08-25T12:00:00+00:00",
    }
    if last_changed is not None:
        result["last_changed"] = last_changed
    return result


HOME_STATES: list[dict[str, Any]] = [
    _state("binary_sensor.front_door", "on", "Front Door", device_class="door"),
    _state("binary_sensor.kitchen_window", "off", "Kitchen Window", device_class="window"),
    _state("cover.garage_door", "open", "Garage Door", device_class="garage"),
    _state("binary_sensor.basement_hatch", "on", "Basement Hatch", device_class="opening"),
    _state("binary_sensor.patio_door", "on", "Patio Door"),
    _state("binary_sensor.doorbell_motion", "on", "Doorbell Motion", device_class="motion"),
    _state("binary_sensor.hall_smoke", "on", "Hall Smoke", device_class="smoke"),
    _state("binary_sensor.utility_co", "on", "Utility CO", device_class="carbon_monoxide"),
    _state("binary_sensor.laundry_leak", "on", "Laundry Leak", device_class="moisture"),
    _state("binary_sensor.hvac_problem", "on", "HVAC Problem", device_class="problem"),
    _state("binary_sensor.hub_connected", "off", "Hub Connected", device_class="connectivity"),
    _state("binary_sensor.family_room_occupancy", "on", "Family Room", device_class="occupancy"),
    _state(
        "sensor.front_lock_battery", "15", "Front Lock Battery", device_class="battery", unit="%"
    ),
    _state(
        "sensor.thermostat_battery", "80", "Thermostat Battery", device_class="battery", unit="%"
    ),
    _state("sensor.phone_charging", "charging", "Phone Charging", device_class="battery_charging"),
    _state(
        "sensor.backup_battery_voltage",
        "3.1",
        "Backup Battery Voltage",
        device_class="voltage",
        unit="V",
    ),
    _state("binary_sensor.remote_battery", "on", "Remote Battery", device_class="battery"),
    _state("sensor.named_battery", "5", "Named Battery", unit="%"),
    _state("light.kitchen", "on", "Kitchen Light", brightness=128),
    _state("light.bedroom", "off", "Bedroom Light", brightness=0),
    _state(
        "sensor.garage_temperature",
        "68.2",
        "Garage Temperature",
        device_class="temperature",
        unit="°F",
    ),
    _state("sensor.kitchen_humidity", "44", "Kitchen Humidity", device_class="humidity", unit="%"),
    _state("sensor.home_power", "550", "Home Power", device_class="power", unit="W"),
    _state("sensor.daily_energy", "12.4", "Daily Energy", device_class="energy", unit="kWh"),
    _state("climate.downstairs", "heat", "Downstairs Thermostat"),
    _state(
        "sensor.offline_bridge",
        "unavailable",
        "Offline Bridge",
        last_changed="2026-08-25T09:00:00+00:00",
    ),
    _state("sensor.missing_reading", "unknown", "Missing Reading", last_changed=None),
    _state(
        "device_tracker.private_phone",
        "home",
        "Private Phone",
        latitude=39.123,
        longitude=-77.456,
        gps_accuracy=4,
        source_type="gps",
    ),
]

_AREA_BY_ENTITY = {
    "binary_sensor.front_door": "entry",
    "binary_sensor.kitchen_window": "kitchen",
    "cover.garage_door": "garage",
    "binary_sensor.basement_hatch": "basement",
    "binary_sensor.patio_door": "kitchen",
    "binary_sensor.doorbell_motion": "entry",
    "binary_sensor.hall_smoke": "entry",
    "binary_sensor.utility_co": "basement",
    "binary_sensor.laundry_leak": "basement",
    "binary_sensor.hvac_problem": "basement",
    "binary_sensor.hub_connected": "entry",
    "binary_sensor.family_room_occupancy": "family_room",
    "sensor.front_lock_battery": "entry",
    "sensor.thermostat_battery": "family_room",
    "light.kitchen": "kitchen",
    "light.bedroom": "bedroom",
    "sensor.garage_temperature": "garage",
    "sensor.kitchen_humidity": "kitchen",
    "climate.downstairs": "family_room",
    "sensor.offline_bridge": "basement",
    "device_tracker.private_phone": "entry",
}

HOME_REGISTRIES = RegistrySnapshot(
    entities=tuple(
        {"entity_id": state["entity_id"], "area_id": _AREA_BY_ENTITY.get(state["entity_id"])}
        for state in HOME_STATES
    ),
    devices=(),
    areas=(
        {"area_id": "entry", "name": "Entry", "floor_id": "ground"},
        {"area_id": "kitchen", "name": "Kitchen", "floor_id": "ground"},
        {"area_id": "garage", "name": "Garage", "floor_id": "ground"},
        {"area_id": "family_room", "name": "Family Room", "floor_id": "ground"},
        {"area_id": "basement", "name": "Basement", "floor_id": "lower"},
        {"area_id": "bedroom", "name": "Bedroom", "floor_id": "upper"},
    ),
    floors=(
        {"floor_id": "lower", "name": "Lower Level", "level": -1},
        {"floor_id": "ground", "name": "Ground Floor", "level": 0},
        {"floor_id": "upper", "name": "Upstairs", "level": 1},
    ),
)
