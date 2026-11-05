"""Deterministic internal redaction candidates; never a declassification decision."""
from collections import Counter
from dataclasses import dataclass
import re
import unicodedata

RULE_VERSION = 'capa.d4.redaction.v1'
MAX_TEXT_BYTES = 64 * 1024
INVALID_INPUT = 'PREVIEW_INPUT_INVALID'
SOURCE_LIMIT = 'PREVIEW_SOURCE_LIMIT'

MARKERS = {
    'literal': '[指定词已遮盖]', 'credential': '[凭据已遮盖]', 'url': '[URL已遮盖]',
    'email': '[邮箱已遮盖]', 'id_number': '[证件号已遮盖]', 'mobile': '[手机号已遮盖]',
    'phone': '[电话号码已遮盖]',
}
_PATTERNS = (
    ('credential', 1, re.compile(r'\b(?:password|secret|api_key|token)\s*[:=]\s*(?:"[^"\r\n]*"|\x27[^\x27\r\n]*\x27|[^\s,，;；]+)')),
    ('credential', 1, re.compile(r'\bbearer\s+[^\s,，;；]+')),
    ('credential', 1, re.compile(r'\beyj[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+\b')),
    ('url', 2, re.compile(r'https?://[^\s<>"\x27，；]+')),
    ('email', 3, re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+")),
    ('id_number', 4, re.compile(r'(?<!\d)[1-9]\d{16}[0-9x](?!\d)')),
    ('mobile', 5, re.compile(r'(?<!\d)(?:\+?86[ -]*)?1[3-9]\d(?:[ -]?\d){8}(?!\d)')),
    ('phone', 6, re.compile(r'(?:电话|tel|phone)\s*[:：]?\s*(?P<value>\+?\d[\d ()-]{5,}\d)')),
)


@dataclass(frozen=True)
class RedactedText:
    text: str | None
    match_counts: tuple[tuple[str, int], ...]


def _matching_view(text: str):
    """Canonical matching only; every normalized character maps to original bounds."""
    chunks, positions = [], []
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text) and (unicodedata.combining(text[end]) or text[end] in 'ﾞﾟ'):
            end += 1
        normalized = unicodedata.normalize('NFKC', text[start:end]).casefold()
        chunks.append(normalized)
        positions.extend([(start, end)] * len(normalized))
        start = end
    return ''.join(chunks), positions


def validate_terms(values: list[str]) -> tuple[str, ...]:
    if type(values) is not list or len(values) > 50:
        raise ValueError(INVALID_INPUT)
    terms, seen, size = [], set(), 0
    for value in values:
        if type(value) is not str or any(unicodedata.category(char).startswith('C') for char in value):
            raise ValueError(INVALID_INPUT)
        value = value.strip()
        if not 1 <= len(value) <= 100:
            raise ValueError(INVALID_INPUT)
        try:
            size += len(value.encode('utf-8'))
        except UnicodeError:
            raise ValueError(INVALID_INPUT) from None
        canonical, _ = _matching_view(value)
        if not canonical or canonical in seen or size > 8 * 1024:
            raise ValueError(INVALID_INPUT)
        seen.add(canonical)
        terms.append(value)
    return tuple(sorted(terms, key=lambda value: (-len(_matching_view(value)[0]), _matching_view(value)[0])))


def redact_text(text: str | None, terms: tuple[str, ...]) -> RedactedText:
    if text is None:
        return RedactedText(None, ())
    if type(text) is not str:
        raise ValueError(SOURCE_LIMIT)
    try:
        if len(text.encode('utf-8')) > MAX_TEXT_BYTES:
            raise ValueError(SOURCE_LIMIT)
    except UnicodeError:
        raise ValueError(SOURCE_LIMIT) from None
    if not text:
        return RedactedText('', ())
    view, mapping = _matching_view(text)
    spans = []
    for value in terms:
        term, _ = _matching_view(value)
        for match in re.finditer(re.escape(term), view):
            spans.append((mapping[match.start()][0], mapping[match.end()-1][1], 0, 'literal'))
    for kind, priority, pattern in _PATTERNS:
        for match in pattern.finditer(view):
            first, last = match.span('value') if kind == 'phone' else match.span()
            spans.append((mapping[first][0], mapping[last-1][1], priority, kind))
    merged = []
    for start, end, priority, kind in sorted(spans, key=lambda value: (value[0], -value[1], value[2])):
        if merged and start < merged[-1][1]:
            prior = merged[-1]
            chosen_priority, chosen_kind = (priority, kind) if priority < prior[2] else (prior[2], prior[3])
            merged[-1] = (prior[0], max(prior[1], end), chosen_priority, chosen_kind)
        else:
            merged.append((start, end, priority, kind))
    result, cursor, counts = [], 0, Counter()
    for start, end, _, kind in merged:
        result.extend((text[cursor:start], MARKERS[kind]))
        counts[kind] += 1
        cursor = end
    result.append(text[cursor:])
    return RedactedText(''.join(result), tuple(sorted(counts.items())))
