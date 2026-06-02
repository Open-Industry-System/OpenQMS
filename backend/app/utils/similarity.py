def compute_similarity(query: str, candidate: str) -> tuple[float, str]:
    """混合相似度：子串命中给基础分，否则走 bigram Jaccard。
    返回 (score, match_reason)。
    """
    q, c = query.lower().strip(), candidate.lower().strip()
    if not q or not c:
        return 0.0, "text_similarity"
    if q in c or c in q:
        return 0.75, "substring_match"

    def _bigrams(s: str) -> set[str]:
        s = s.lower().strip()
        return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()

    a, b = _bigrams(query), _bigrams(candidate)
    if not a or not b:
        return 0.0, "text_similarity"
    score = len(a & b) / len(a | b)
    return score, "text_similarity"
