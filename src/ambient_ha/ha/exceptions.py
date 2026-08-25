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


class HomeAssistantAuthorizationError(HomeAssistantError):
    """Credentials are valid but lack permission for a requested read."""

    code = "permission_denied"
    reachable = True
    authenticated = True


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


class HomeAssistantRecorderUnavailable(HomeAssistantError):
    """Recorder-backed state history cannot be read on this installation."""

    code = "recorder_unavailable"
    reachable = True
    authenticated = True


class HomeAssistantLogbookUnavailable(HomeAssistantError):
    """Logbook data cannot be read on this installation."""

    code = "logbook_unavailable"
    reachable = True
    authenticated = True


class HomeAssistantQueryError(HomeAssistantError):
    """A bounded historical query is invalid before it reaches Home Assistant."""

    reachable = True
    authenticated = True

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
