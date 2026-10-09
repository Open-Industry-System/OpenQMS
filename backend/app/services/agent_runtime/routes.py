"""Exact dedicated runtime routes; additions must explicitly register admission."""
RUNTIME_ROUTES = frozenset({
    ("POST", "/api/agent/runtime/claim"),
    ("GET", "/api/agent/runtime/capabilities"),
    ("GET", "/api/agent/runtime/capa/context"),
    ("POST", "/api/agent/runtime/messages/claim"),
    ("POST", "/api/agent/runtime/messages/ack"),
    ("POST", "/api/agent/runtime/events"),
    ("POST", "/api/agent/runtime/results"),
    ("POST", "/api/agent/runtime/finish"),
    ("POST", "/api/agent/runtime/checkpoints"),
    ("GET", "/api/agent/runtime/messages/history"),
})
RUNTIME_PATHS = frozenset(path for _, path in RUNTIME_ROUTES)
RUNTIME_JWT_ROUTES = RUNTIME_ROUTES - {("POST", "/api/agent/runtime/claim")}
