import re
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


def semantic_version(value: object) -> tuple[int, int, int]:
    assert isinstance(value, str)
    parts = value.split(".")
    assert len(parts) == 3
    return int(parts[0]), int(parts[1]), int(parts[2])


def test_home_assistant_app_metadata_is_safe_and_never_leads_package_version() -> None:
    repository = load_yaml(REPOSITORY_ROOT / "repository.yaml")
    config = load_yaml(REPOSITORY_ROOT / "homeassistant-addon" / "config.yaml")

    assert repository["url"] == "https://github.com/ambient-home-systems/ambient-ha-mcp"
    assert semantic_version(config["version"]) <= semantic_version(ambient_ha.__version__)
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
    schema = config["schema"]
    assert isinstance(options, dict)
    assert isinstance(schema, dict)
    assert "home_assistant_token" not in options
    if semantic_version(config["version"]) < semantic_version(ambient_ha.__version__):
        # Source code may lead the catalog only while new runtime options remain
        # unadvertised. Otherwise users of the old image could configure keys it rejects.
        assert "read_only" not in options
        assert "control_enabled" not in options
        assert "read_only" not in schema
        assert "control_enabled" not in schema
    else:
        assert options["read_only"] is True
        assert options["control_enabled"] is False
        assert options["allowed_switch_entities"] == []
        assert options["allowed_scene_entities"] == []
        assert options["allowed_script_entities"] == []
    assert "policy_file" not in options


def test_container_uses_runtime_selecting_launcher() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "ambient_ha.launcher"]' in dockerfile
    assert "AMBIENT_RUNTIME_USER=ambient" in dockerfile
    assert "USER ambient" not in dockerfile
    assert "user: ambient" in compose


def test_app_pr_build_never_publishes_or_advertises_a_candidate() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "home-assistant-app.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in workflow
    assert "branches: [main]" not in workflow
    assert "push: false" in workflow
    assert "Publish multi-architecture manifest" not in workflow
    assert "APP_VERSION: ${{ steps.package.outputs.version }}" in workflow
    assert 'image="${APP_IMAGE//\\"/}"' in workflow
    assert 'version="${APP_VERSION//\\"/}"' in workflow
    assert 'echo "version=${version}" >> "${GITHUB_OUTPUT}"' in workflow


def test_versioned_release_precedes_separate_catalog_promotion() -> None:
    publish = (
        REPOSITORY_ROOT / ".github" / "workflows" / "publish-home-assistant-app.yml"
    ).read_text(encoding="utf-8")
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'tags:\n      - "v*.*.*"' in publish
    assert 'if [[ "${version}" != "${package_version}" ]]' in publish
    assert "push: true" in publish
    assert "Publish versioned multi-architecture manifest" in publish
    assert "linux/amd64" in publish
    assert "linux/arm64" in publish
    assert "image-tags: ${{ needs.prepare.outputs.version }}" in publish
    assert "            latest" not in publish
    assert "Verify advertised App image exists" in ci
    assert 'docker buildx imagetools inspect "${image}:${version}"' in ci
    assert "linux/amd64" in ci
    assert "linux/arm64" in ci


def test_phase_6_6_report_lists_every_read_only_tool_once() -> None:
    report = (REPOSITORY_ROOT / "docs" / "phase-6-6-live-validation.md").read_text(encoding="utf-8")
    listed_tools = re.findall(r"^\| `(ha_[a-z0-9_]+)` \|", report, flags=re.MULTILINE)

    assert len(listed_tools) == 24
    assert len(set(listed_tools)) == 24


def test_phase_6_5_default_policy_denies_every_non_read_operation() -> None:
    engine = PolicyEngine(PolicyConfig(read_only=True))

    for operation in OperationClass:
        decision = engine.evaluate(operation)
        if operation is OperationClass.READ:
            assert decision.decision is PolicyAction.ALLOW
        else:
            assert decision.decision is PolicyAction.DENY
            assert decision.matched_rule == "hard_boundary.read_only"
