import json
import logging

from ambient_ha.logging import JsonFormatter, configure_logging, redact_secrets


def test_common_secret_forms_are_redacted() -> None:
    token = "this-is-a-sensitive-token"
    assert token not in redact_secrets(f"Authorization: Bearer {token}")
    assert token not in redact_secrets(f"token={token}")
    assert token not in redact_secrets(f"Bearer {token}")
    redacted_json = redact_secrets(f'{{"type":"auth","access_token":"{token}"}}')
    redacted_repr = redact_secrets(f"{{'access_token': '{token}'}}")
    assert token not in redacted_json
    assert json.loads(redacted_json)["access_token"] == "[REDACTED]"
    assert token not in redacted_repr
    assert redacted_repr == "{'access_token': '[REDACTED]'}"


def test_json_formatter_includes_context_without_token() -> None:
    token = "this-is-a-sensitive-token"
    record = logging.LogRecord(
        name="ambient_ha.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request failed Authorization: Bearer %s",
        args=(token,),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["logger"] == "ambient_ha.test"
    assert token not in payload["message"]
    assert "timestamp" in payload


def test_websocket_dependency_loggers_never_inherit_debug() -> None:
    root = logging.getLogger()
    client_logger = logging.getLogger("websockets.client")
    server_logger = logging.getLogger("websockets.server")
    previous_handlers = root.handlers[:]
    previous_root_level = root.level
    previous_client_level = client_logger.level
    previous_server_level = server_logger.level
    try:
        configure_logging("DEBUG")

        assert client_logger.getEffectiveLevel() >= logging.INFO
        assert server_logger.getEffectiveLevel() >= logging.INFO
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_root_level)
        client_logger.setLevel(previous_client_level)
        server_logger.setLevel(previous_server_level)
