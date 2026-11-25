"""Response language support (German / English).

Service code keeps its original (Chinese) message strings so that behaviour and
tests stay unchanged. Messages are translated on the way out, based on the
request's ``Accept-Language`` header (see ``middleware.py``).

``messages.json`` holds ``[source, de, en]`` triples. ``{}`` marks a value that
was interpolated into the message (f-string / ``str.format``); ``{0}``/``{1}``
in a translation reorder those values.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

SUPPORTED = ("de", "en")
# UI language of the current request ("de"/"en"), set by the middleware.
request_language: ContextVar[str | None] = ContextVar("request_language", default=None)

_OUTPUT_DIRECTIVE = {
    "de": (
        "\n\n[Output language] The user's interface language is German. Respond entirely in "
        "German (Deutsch): every human-readable text value must be German. Keep the required "
        "JSON structure, keys and enum values unchanged.\n"
    ),
    "en": (
        "\n\n[Output language] The user's interface language is English. Respond entirely in "
        "English: every human-readable text value must be English. Keep the required JSON "
        "structure, keys and enum values unchanged.\n"
    ),
}
_CJK = re.compile(r"[\u4e00-\u9fff]")
# Patterns with very short fixed text would match arbitrary user data.
_MIN_PATTERN_LITERAL = 4


def _compile(template: str) -> re.Pattern[str]:
    literal = template.replace("{{", "\0").replace("}}", "\1")
    parts = [re.escape(p).replace("\0", "\\{").replace("\1", "\\}") for p in literal.split("{}")]
    return re.compile("^" + "(.+?)".join(parts) + "$", re.S)


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, tuple[str, str]], list[tuple[re.Pattern[str], str, str]]]:
    rows = json.loads((Path(__file__).with_name("messages.json")).read_text(encoding="utf-8"))
    exact: dict[str, tuple[str, str]] = {}
    patterns: list[tuple[int, re.Pattern[str], str, str]] = []
    for source, de, en in rows:
        if "{}" not in source.replace("{{", "").replace("}}", ""):
            exact.setdefault(source.replace("{{", "{").replace("}}", "}"), (de, en))
            continue
        fixed = source.replace("{}", "")
        if len(_CJK.findall(fixed)) < _MIN_PATTERN_LITERAL:
            continue
        patterns.append((len(fixed), _compile(source), de, en))
    patterns.sort(key=lambda p: -p[0])
    return exact, [(rx, de, en) for _, rx, de, en in patterns]


def pick_language(accept_language: str | None) -> str | None:
    """Return 'de' or 'en' for the first supported language tag, else None."""
    if not accept_language:
        return None
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        if primary in SUPPORTED:
            return primary
    return None


def translate(text: str, lang: str | None) -> str:
    """Translate one known backend message; unknown text is returned unchanged."""
    if lang not in SUPPORTED or not text or not _CJK.search(text):
        return text
    idx = 0 if lang == "de" else 1
    exact, patterns = _catalog()
    hit = exact.get(text)
    if hit:
        return hit[idx]
    for rx, de, en in patterns:
        m = rx.match(text)
        if m:
            values = [translate(v, lang) for v in m.groups()]
            return (de, en)[idx].format(*values)
    return text


def translate_json(value: object, lang: str | None) -> object:
    """Recursively translate all string values of a decoded JSON document."""
    if isinstance(value, str):
        return translate(value, lang)
    if isinstance(value, list):
        return [translate_json(v, lang) for v in value]
    if isinstance(value, dict):
        return {k: translate_json(v, lang) for k, v in value.items()}
    return value


def with_output_language(prompt: str) -> str:
    """Append an output-language instruction for LLM prompts (no-op outside requests)."""
    lang = request_language.get()
    if lang not in _OUTPUT_DIRECTIVE or "Output language" in prompt:
        return prompt
    return prompt + _OUTPUT_DIRECTIVE[lang]
