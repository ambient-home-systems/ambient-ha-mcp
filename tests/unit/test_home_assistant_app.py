from pathlib import Path

import yaml

import ambient_ha
from ambient_ha.policy.config import PolicyConfig
from ambient_ha.policy.engine import PolicyEngine
from ambient_ha.policy.models import OperationClass, PolicyAction

REPOSITORY_ROOT = Path(__file__).parents[2]


def load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_home_assistant_app_metadata_is_safe_and_version_aligned() -> None:
    repository = load_yaml(REPOSITORY_ROOT / "repository.yaml")
    config = load_yaml(REPOSITORY_ROOT / "homeassistant-addon" / "config.yaml")

    assert repository["url"] == "https://github.com/ambient-home-systems/ambient-ha-mcp"
    assert config["version"] == ambient_ha.__version__
    assert config["arch"] == ["aarch64", "amd64"]
    assert config["image"] == "ghcr.io/ambient-home-systems/ambient-ha-mcp"
    assert config["homeassistant_api"] is True
    assert config.get("hassio_api", False) is False
    assert config.get("auth_api", False) is False
    assert config.get("docker_api", False) is False
    assert config.get("full_access", False) is False
    assert config.get("host_network", False) is False
    assert config.get("ingress", False) is False
    assert config.get("apparmor", True) is True
    assert config["stage"] == "experimental"
    assert config["ports"] == {"8000/tcp": None}
    assert "map" not in config
    assert "privileged" not in config
    assert "devices" not in config
    assert config["environment"] == {"AMBIENT_RUNTIME_MODE": "home_assistant_app"}

    options = config["options"]
    assert isinstance(options, dict)
    assert "home_assistant_token" not in options
    assert "read_only" not in options
    assert "policy_file" not in options


def test_container_uses_runtime_selecting_launcher() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "ambient_ha.launcher"]' in dockerfile
    assert "USER ambient" in dockerfile


def test_phase_6_5_default_policy_denies_every_non_read_operation() -> None:
    engine = PolicyEngine(PolicyConfig(read_only=True))

    for operation in OperationClass:
        decision = engine.evaluate(operation)
        if operation is OperationClass.READ:
            assert decision.decision is PolicyAction.ALLOW
        else:
            assert decision.decision is PolicyAction.DENY
            assert decision.matched_rule == "hard_boundary.read_only"
