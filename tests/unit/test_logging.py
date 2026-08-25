import json
import logging

from ambient_ha.logging import JsonFormatter, redact_secrets


def test_common_secret_forms_are_redacted() -> None:
    token = "this-is-a-sensitive-token"
    assert token not in redact_secrets(f"Authorization: Bearer {token}")
    assert token not in redact_secrets(f"token={token}")
    assert token not in redact_secrets(f"Bearer {token}")


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
