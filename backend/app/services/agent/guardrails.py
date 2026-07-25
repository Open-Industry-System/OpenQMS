"""Guardrails: input heuristic + output sanitization. Structural guarantees (tool whitelist,
fixed system prompt, scope-from-context) are enforced by the harness/main loop, not here."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

# Heuristic injection patterns (P0 minimal; model-level detection is P1+).
_INJECTION_PATTERNS = [
    re.compile(r"忽略.{0,10}指令", re.IGNORECASE),
    re.compile(r"你是.{0,10}(新|另一个|新的).{0,5}系统", re.IGNORECASE),
    re.compile(r"输出.{0,10}factory_id", re.IGNORECASE),
    re.compile(r"忽略.{0,10}以上", re.IGNORECASE),
]

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

_MAX_OUTPUT_CHARS = 8000


@dataclass
class GuardrailResult:
    ok: bool
    reason: str | None = None


def check_input(message: str) -> GuardrailResult:
    for p in _INJECTION_PATTERNS:
        if p.search(message or ""):
            return GuardrailResult(False, reason=f"blocked injection pattern: {p.pattern}")
    return GuardrailResult(True)


def _redact(value, bound_factory_id: uuid.UUID):
    if isinstance(value, str):
        def _sub(m):
            u = uuid.UUID(m.group(0))
            return "<redacted>" if u != bound_factory_id else m.group(0)
        value = _UUID_RE.sub(_sub, value)
        if len(value) > _MAX_OUTPUT_CHARS:
            value = value[:_MAX_OUTPUT_CHARS] + "...<truncated>"
        return value
    if isinstance(value, dict):
        return {k: _redact(v, bound_factory_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, bound_factory_id) for v in value]
    return value


def sanitize_output(tool_result: dict, factory_id: uuid.UUID) -> dict:
    return _redact(tool_result, factory_id)
