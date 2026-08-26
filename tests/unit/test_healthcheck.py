import pytest

from ambient_ha import healthcheck


class HealthyResponse:
    status = 200

    def __enter__(self) -> "HealthyResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_healthcheck_drops_container_privileges_before_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        healthcheck,
        "drop_container_privileges",
        lambda: calls.append("drop"),
    )
    monkeypatch.setattr(
        healthcheck,
        "urlopen",
        lambda *args, **kwargs: calls.append("probe") or HealthyResponse(),
    )
    monkeypatch.setattr(
        healthcheck.json,
        "load",
        lambda response: {"application_running": True},
    )

    healthcheck.main()

    assert calls == ["drop", "probe"]


def test_healthcheck_fails_closed_when_privilege_drop_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_drop() -> None:
        raise healthcheck.RuntimeConfigurationError("sanitized")

    monkeypatch.setattr(healthcheck, "drop_container_privileges", fail_drop)
    monkeypatch.setattr(
        healthcheck,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("probe must not run"),
    )

    with pytest.raises(SystemExit) as captured:
        healthcheck.main()

    assert captured.value.code == 1
