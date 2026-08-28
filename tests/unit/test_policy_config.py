from pathlib import Path

import pytest
from pydantic import ValidationError

from ambient_ha.policy import (
    OperationClass,
    PolicyAction,
    PolicyConfig,
    ValueLimits,
    effective_policy_config,
    load_policy_file,
)


def test_safe_defaults_are_complete_and_read_only() -> None:
    config = PolicyConfig()

    assert config.read_only is True
    assert config.global_default is PolicyAction.DENY
    assert config.operation_rules[OperationClass.READ] is PolicyAction.ALLOW
    assert config.operation_rules[OperationClass.ADMINISTRATIVE] is PolicyAction.DENY
    assert config.domain_rules["switch"] is PolicyAction.DENY
    assert config.domain_rules["scene"] is PolicyAction.CONFIRM_REQUIRED
    assert config.domain_rules["script"] is PolicyAction.DENY
    assert config.limits.max_entities_per_action == 20
    assert config.limits.max_operations_per_request == 10


def test_strict_toml_policy_file_loads_and_normalizes(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        """
read_only = false
global_default = "deny"

[operation_rules]
read = "allow"
normal_control = "deny"

[domain_rules]
LIGHT = "allow"
switch = "deny"

[entity_rules]
"SWITCH.Desk_Lamp" = "allow"

[protected_entities]
"cover.Main_Garage" = "deny"

[limits]
max_entities_per_action = 5
max_operations_per_request = 3

[values]
climate_min_celsius = 10
climate_max_celsius = 28
climate_min_fahrenheit = 50
climate_max_fahrenheit = 82
allowed_hvac_modes = ["off", "heat", "cool"]
max_media_volume = 0.6
min_brightness_percent = 0
max_brightness_percent = 90
min_color_temperature_kelvin = 2000
max_color_temperature_kelvin = 6500
min_fan_percentage = 0
max_fan_percentage = 80
""",
        encoding="utf-8",
    )

    config = load_policy_file(path)

    assert config.read_only is False
    assert config.domain_rules["light"] is PolicyAction.ALLOW
    assert config.entity_rules["switch.desk_lamp"] is PolicyAction.ALLOW
    assert config.protected_entities["cover.main_garage"] is PolicyAction.DENY
    assert config.limits.max_entities_per_action == 5
    assert config.values.max_media_volume == 0.6


@pytest.mark.parametrize(
    "payload",
    [
        'unknown_key = "unsafe"\n',
        'global_default = "permit"\n',
        '[operation_rules]\nread = "allow"\nsuperuser = "allow"\n',
        '[entity_rules]\n"not an entity" = "allow"\n',
        '[protected_entities]\n"lock.front" = "allow"\n',
        "[limits]\nmax_entities_per_action = -1\n",
        '[operation_rules]\nread = "deny"\n',
        "[values]\nclimate_min_celsius = 30\nclimate_max_celsius = 10\n",
    ],
)
def test_unsafe_or_unknown_policy_configuration_is_rejected(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises((ValidationError, ValueError)):
        load_policy_file(path)


def test_duplicate_case_normalized_rules_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyConfig(domain_rules={"LIGHT": "allow", "light": "deny"})


def test_invalid_value_bounds_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ValueLimits(min_fan_percentage=80, max_fan_percentage=20)
    with pytest.raises(ValidationError):
        ValueLimits(allowed_hvac_modes=[])


def test_environment_read_only_cannot_be_disabled_by_policy_file(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text("read_only = false\n", encoding="utf-8")

    environment_boundary = effective_policy_config(environment_read_only=True, path=path)
    both_disabled = effective_policy_config(environment_read_only=False, path=path)
    no_file = effective_policy_config(environment_read_only=False, path=None)

    assert environment_boundary.read_only is True
    assert both_disabled.read_only is False
    assert no_file.read_only is False


def test_missing_or_malformed_policy_file_fails_startup_loading(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="could not be read"):
        load_policy_file(tmp_path / "missing.toml")
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("[broken", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid TOML"):
        load_policy_file(malformed)
