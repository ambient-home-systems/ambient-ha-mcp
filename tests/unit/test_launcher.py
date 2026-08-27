import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ambient_ha import launcher


def write_options(path: Path, options: object) -> None:
    path.write_text(json.dumps(options), encoding="utf-8")


def test_app_runtime_uses_supervisor_auth_and_forces_read_only(tmp_path: Path) -> None:
    options_path = tmp_path / "options.json"
    write_options(
        options_path,
        {
            "log_level": "WARNING",
            "registry_cache_ttl_seconds": 120,
            "ignored_diagnostic_entities": ["sensor.private", "device_tracker.phone"],
            "mcp_allowed_hosts": ["homeassistant.local", "homeassistant.local:*"],
        },
    )
    environ = {
        "SUPERVISOR_TOKEN": "supervisor-secret",
        "HOME_ASSISTANT_URL": "https://untrusted.example",
        "HOME_ASSISTANT_WEBSOCKET_URL": "wss://untrusted.example/api/websocket",
        "HOME_ASSISTANT_TOKEN": "old-token",
        "READ_ONLY": "false",
        "MCP_HOST": "127.0.0.1",
        "POLICY_FILE": "/data/unsafe-policy.json",
    }

    launcher.configure_home_assistant_app_environment(options_path=options_path, environ=environ)

    assert environ["HOME_ASSISTANT_URL"] == "http://supervisor/core"
    assert environ["HOME_ASSISTANT_WEBSOCKET_URL"] == "ws://supervisor/core/websocket"
    assert environ["HOME_ASSISTANT_WEBSOCKET_URL"] != "ws://supervisor/core/api/websocket"
    assert environ["HOME_ASSISTANT_WEBSOCKET_USE_SYSTEM_PROXY"] == "false"
    assert environ["HOME_ASSISTANT_TOKEN"] == "supervisor-secret"
    assert environ["READ_ONLY"] == "true"
    assert environ["MCP_HOST"] == "0.0.0.0"  # noqa: S104
    assert environ["MCP_PORT"] == "8000"
    assert environ["MCP_ALLOWED_ORIGINS"] == ""
    assert environ["LOG_LEVEL"] == "WARNING"
    assert environ["REGISTRY_CACHE_TTL_SECONDS"] == "120"
    assert environ["IGNORED_DIAGNOSTIC_ENTITIES"] == ("sensor.private,device_tracker.phone")
    assert environ["MCP_ALLOWED_HOSTS"] == "homeassistant.local,homeassistant.local:*"
    assert "POLICY_FILE" not in environ
    assert "supervisor-secret" not in options_path.read_text(encoding="utf-8")


def test_container_bootstrap_drops_privileges_before_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = {"uid": 0}
    calls: list[tuple[object, ...]] = []
    account = SimpleNamespace(pw_name="ambient", pw_uid=987, pw_gid=986, pw_dir="/app")

    monkeypatch.setattr(launcher.os, "geteuid", lambda: identity["uid"])
    monkeypatch.setattr(launcher.pwd, "getpwnam", lambda user: account)
    monkeypatch.setattr(
        launcher.os,
        "initgroups",
        lambda user, gid: calls.append(("initgroups", user, gid)),
    )
    monkeypatch.setattr(launcher.os, "setgid", lambda gid: calls.append(("setgid", gid)))

    def fake_setuid(uid: int) -> None:
        calls.append(("setuid", uid))
        identity["uid"] = uid

    monkeypatch.setattr(launcher.os, "setuid", fake_setuid)
    environ = {launcher.RUNTIME_USER_ENVIRONMENT_KEY: "ambient", "HOME": "/root"}

    launcher.drop_container_privileges(environ=environ)

    assert calls == [
        ("initgroups", "ambient", 986),
        ("setgid", 986),
        ("setuid", 987),
    ]
    assert environ["HOME"] == "/app"


def test_container_bootstrap_rejects_runtime_user_override() -> None:
    with pytest.raises(launcher.RuntimeConfigurationError, match="Invalid container runtime user"):
        launcher.drop_container_privileges(environ={launcher.RUNTIME_USER_ENVIRONMENT_KEY: "root"})


def test_app_launcher_configures_then_drops_privileges_before_starting_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("AMBIENT_RUNTIME_MODE", launcher.APP_RUNTIME_MODE)
    monkeypatch.setattr(
        launcher,
        "configure_home_assistant_app_environment",
        lambda: calls.append("configure"),
    )
    monkeypatch.setattr(
        launcher,
        "drop_container_privileges",
        lambda: calls.append("drop"),
    )
    monkeypatch.setattr(launcher, "server_main", lambda: calls.append("serve"))

    launcher.main()

    assert calls == ["configure", "drop", "serve"]


def test_app_runtime_requires_supervisor_auth_without_disclosing_values(tmp_path: Path) -> None:
    options_path = tmp_path / "options.json"
    write_options(options_path, {})

    with pytest.raises(launcher.RuntimeConfigurationError) as captured:
        launcher.configure_home_assistant_app_environment(
            options_path=options_path,
            environ={"HOME_ASSISTANT_TOKEN": "must-not-appear"},
        )

    assert str(captured.value) == "Supervisor authentication is unavailable"
    assert "must-not-appear" not in str(captured.value)


@pytest.mark.parametrize(
    "options",
    [
        {"home_assistant_token": "not-allowed"},
        {"read_only": False},
        {"mcp_allowed_hosts": ["valid", ""]},
        {"mcp_allowed_hosts": ["*"]},
        {"mcp_allowed_hosts": "homeassistant.local"},
        {"ignored_diagnostic_entities": "sensor.one"},
        {"registry_cache_ttl_seconds": 60.5},
    ],
)
def test_app_runtime_rejects_unknown_or_invalid_options(
    tmp_path: Path, options: dict[str, object]
) -> None:
    options_path = tmp_path / "options.json"
    write_options(options_path, options)

    with pytest.raises(launcher.RuntimeConfigurationError):
        launcher.configure_home_assistant_app_environment(
            options_path=options_path,
            environ={"SUPERVISOR_TOKEN": "secret"},
        )


def test_launcher_preserves_standalone_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    started = False

    def fake_server_main() -> None:
        nonlocal started
        started = True

    monkeypatch.delenv("AMBIENT_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(launcher, "server_main", fake_server_main)

    launcher.main()

    assert started is True


def test_launcher_fails_closed_for_unknown_runtime_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AMBIENT_RUNTIME_MODE", "unexpected")

    with pytest.raises(SystemExit, match="unsupported runtime mode"):
        launcher.main()
