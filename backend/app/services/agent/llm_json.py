"""Shared JSON-from-LLM-text util + size cap.

Used by provider_adapter.complete_json (agent base) and the legacy
LLMProvider.complete (llm_provider.py) so both parse identically.
"""
import json

MAX_RESPONSE_BYTES = 10_240  # 10KB


def extract_json(text: str) -> dict:
    """Parse JSON from an LLM response, tolerating ```json code fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
