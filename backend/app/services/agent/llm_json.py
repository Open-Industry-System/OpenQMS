"""Shared JSON-from-LLM-text util + size cap.

Used by provider_adapter.complete_json (agent base) and the legacy
LLMProvider.complete (llm_provider.py) so both parse identically.
"""
import json
from typing import Any

MAX_RESPONSE_BYTES = 10_240  # 10KB


def extract_json(text: str) -> Any:
    """Parse JSON from an LLM response.

    Tolerates:
    - ```json / ``` fences
    - leading/trailing prose around a single top-level object or array
      (common with small local models that ignore "JSON only")

    Returns the parsed value (dict, list, or scalar). Callers that require a
    dict (e.g. doc-gate impact) still type-check after this returns.
    """
    text = (text or "").strip()
    if not text:
        raise json.JSONDecodeError("Expecting value", text, 0)

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slice from first { or [ through last matching closer.
    start_obj = text.find("{")
    start_arr = text.find("[")
    candidates: list[int] = [i for i in (start_obj, start_arr) if i >= 0]
    if not candidates:
        raise json.JSONDecodeError("Expecting value", text, 0)
    start = min(candidates)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise json.JSONDecodeError("Expecting value", text, 0)
    return json.loads(text[start : end + 1])
