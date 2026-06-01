import re


def extract_keywords(text: str, min_length: int = 2) -> list[str]:
    """Extract keywords from text.

    Strategy (stdlib only, no jieba dependency):
    - Split by Chinese punctuation, English punctuation, spaces, newlines
    - Filter out pure numeric tokens and tokens shorter than min_length
    - Deduplicate preserving order
    """
    if not text:
        return []

    # Split on Chinese/English punctuation, whitespace, newlines
    tokens = re.split(r"[；，。、！？：；\s,.!?;:\n\r\t]+", text)

    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token or len(token) < min_length:
            continue
        if token.isdigit():
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)

    return result
