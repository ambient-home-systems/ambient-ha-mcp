"""Normalized Home Assistant failures that never include credentials."""


class HomeAssistantError(Exception):
    """Base class for safe, user-facing Home Assistant client failures."""

    code = "home_assistant_error"
    reachable = False
    authenticated = False


class HomeAssistantInvalidURL(HomeAssistantError):
    """The configured Home Assistant URL cannot be used."""

    code = "invalid_url"


class HomeAssistantAuthenticationError(HomeAssistantError):
    """Home Assistant rejected the configured credentials."""

    code = "authentication_failed"
    reachable = True


class HomeAssistantTimeoutError(HomeAssistantError):
    """Home Assistant did not respond within the configured timeout."""

    code = "timeout"


class HomeAssistantTLSFailure(HomeAssistantError):
    """TLS negotiation or certificate verification failed."""

    code = "tls_failure"


class HomeAssistantUnreachableError(HomeAssistantError):
    """A connection to Home Assistant could not be established."""

    code = "unreachable"


class HomeAssistantUnexpectedResponse(HomeAssistantError):
    """Home Assistant returned an unsupported or malformed response."""

    code = "unexpected_response"
    reachable = True
