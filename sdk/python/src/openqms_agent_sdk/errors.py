"""Sanitized diagnostics; kinds are internal, never server business codes."""

_SAFE_OPERATIONS = frozenset({
    "unknown", "config", "claim", "capabilities", "claim_messages", "ack_messages",
    "capa_context", "record_event", "save_result", "save_checkpoint",
    "message_history", "finish", "close",
})
_SAFE_KINDS = frozenset({
    "unknown", "invalid_config", "invalid_timeout", "invalid_response_budget",
    "invalid_url", "invalid_tenant", "invalid_request", "invalid_uuid",
    "invalid_type", "invalid_value", "request_too_large", "timeout", "dns",
    "connection", "tls", "http_status", "redirect", "invalid_response",
    "invalid_json", "invalid_utf8", "duplicate_key", "schema", "binding",
    "unsupported_encoding", "response_too_large", "outcome_unknown",
    "client_closed", "client_busy", "transport", "deadline", "dns_busy", "connection_closed",
})


class SDKError(Exception):
    """Only bounded internal metadata is retained in attrs, args and repr."""

    def __init__(self, operation, *, kind, status=None,
                 may_have_been_sent=False, outcome_unknown=False):
        self.operation = operation if type(operation) is str and operation in _SAFE_OPERATIONS else "unknown"
        self.kind = kind if type(kind) is str and kind in _SAFE_KINDS else "unknown"
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        self.may_have_been_sent = may_have_been_sent is True
        self.outcome_unknown = isinstance(self, UnknownOutcome) or outcome_unknown is True
        super().__init__(
            f"operation={self.operation} kind={self.kind} status={self.status} "
            f"may_have_been_sent={self.may_have_been_sent} outcome_unknown={self.outcome_unknown}"
        )


class ConfigError(SDKError):
    """Invalid local configuration."""


class ValidationError(SDKError):
    """Invalid outgoing protocol value."""


class TransportError(SDKError):
    """Communication failure."""


class RequestTimeout(TransportError):
    """Operation deadline expired."""


class HTTPError(SDKError):
    """An HTTP status rejected the operation."""


class ProtocolError(SDKError):
    """Response is incompatible with the supported protocol."""


class ResponseTooLarge(ProtocolError):
    """Response resource budget exceeded."""


class UnknownOutcome(SDKError):
    """The operation may have completed without trustworthy confirmation."""


class ClientClosed(SDKError):
    """Operation attempted on a closed client."""


class ClientBusy(SDKError):
    """Concurrent operation is unsupported."""
