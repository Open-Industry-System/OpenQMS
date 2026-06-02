import pytest
from app.utils.similarity import compute_similarity


def test_substring_match():
    score, reason = compute_similarity("焊接不良", "焊接不良原因分析")
    assert score == 0.75
    assert reason == "substring_match"


def test_bigram_jaccard():
    # "密封失效" vs "密封不良" — bigram Jaccard = 1/5 = 0.2，不足
    # 改用共享 bigram 更多的词对来测试 Jaccard 路径
    score, reason = compute_similarity("焊接参数偏移", "焊接参数失控")
    assert score > 0.3
    assert score < 1.0
    assert reason == "text_similarity"


def test_no_match():
    score, reason = compute_similarity("abc", "xyz")
    assert score == 0.0
    assert reason == "text_similarity"


def test_empty_query():
    score, reason = compute_similarity("", "anything")
    assert score == 0.0
    assert reason == "text_similarity"
