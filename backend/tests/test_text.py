from app.utils.text import extract_keywords


def test_chinese_punctuation_split():
    result = extract_keywords("焊接虚焊；参数偏移，温度过高")
    assert result == ["焊接虚焊", "参数偏移", "温度过高"]


def test_english_space_split():
    result = extract_keywords("welding defect parameter drift")
    assert result == ["welding", "defect", "parameter", "drift"]


def test_mixed_text():
    result = extract_keywords("焊接虚焊 welding defect；温度异常")
    assert "焊接虚焊" in result
    assert "welding" in result
    assert "defect" in result
    assert "温度异常" in result


def test_filters_short_tokens():
    result = extract_keywords("A B 你好 world")
    assert "A" not in result
    assert "B" not in result
    assert "你好" in result
    assert "world" in result


def test_filters_numbers():
    result = extract_keywords("温度 123 偏移 456")
    assert result == ["温度", "偏移"]


def test_empty_string():
    result = extract_keywords("")
    assert result == []


def test_dedup_preserves_order():
    result = extract_keywords("虚焊；虚焊；偏移")
    assert result == ["虚焊", "偏移"]


def test_min_length_param():
    result = extract_keywords("A BC DEF", min_length=3)
    assert result == ["DEF"]
