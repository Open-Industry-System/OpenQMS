import dataclasses

import pytest


def redact(raw, terms=()):
    from app.services.capa_d4_redaction import redact_text, validate_terms
    return redact_text(raw, validate_terms(list(terms)))


@pytest.mark.parametrize('raw,terms,want,kind', [
    ('联系 sam@example.test，扭矩 10 N·m', (), '联系 [邮箱已遮盖]，扭矩 10 N·m', 'email'),
    ('号码 +86 138-0013-8000，温度85°C', (), '号码 [手机号已遮盖]，温度85°C', 'mobile'),
    ('身份证 11010519491231002X', (), '身份证 [证件号已遮盖]', 'id_number'),
    ('访问 https://example.test/private?id=secret', (), '访问 [URL已遮盖]', 'url'),
    ('Bearer abc123_PRIVATE-token', (), '[凭据已遮盖]', 'credential'),
    ('password=SUPER-SECRET，扭矩10', (), '[凭据已遮盖]，扭矩10', 'credential'),
    ('api_key: sk-private-value', (), '[凭据已遮盖]', 'credential'),
    ('token="quoted private value" 尺寸5', (), '[凭据已遮盖] 尺寸5', 'credential'),
    ('电话：010-12345678，转速2000', (), '电话：[电话号码已遮盖]，转速2000', 'phone'),
    ('客户 A+B 与零件 DC-100', ('A+B',), '客户 [指定词已遮盖] 与零件 DC-100', 'literal'),
    ('客户 [A].* 与零件', ('[A].*',), '客户 [指定词已遮盖] 与零件', 'literal'),
    ('客户ACME', ('acme',), '客户[指定词已遮盖]', 'literal'),
    ('客户ＡＣＭＥ，μm ５', ('acme',), '客户[指定词已遮盖]，μm ５', 'literal'),
    ('客户Straße', ('STRASSE',), '客户[指定词已遮盖]', 'literal'),
    ('客户Café', ('Café',), '客户[指定词已遮盖]', 'literal'),
    ('13800138000 和 13800138000', (), '[手机号已遮盖] 和 [手机号已遮盖]', 'mobile'),
])
def test_fixed_format_and_literal_redaction_preserves_unmatched_technical_text(raw, terms, want, kind):
    output = redact(raw, terms)
    assert output.text == want
    assert dict(output.match_counts)[kind] == (2 if raw.startswith('13800138000 和') else 1)
    assert set(dict(output.match_counts)) <= {'literal', 'credential', 'url', 'email', 'id_number', 'mobile', 'phone'}


def test_overlap_union_does_not_leave_secret_suffix_or_rescan_placeholders():
    output = redact('token=PRIVATE-SUFFIX done', ('PRIVATE',))
    assert output.text == '[指定词已遮盖] done'
    assert dict(output.match_counts) == {'literal': 1}
    assert redact('ABCDEFG then ABC', ('ABC', 'ABCDEFG')).text == '[指定词已遮盖] then [指定词已遮盖]'


@pytest.mark.parametrize('raw', [None, '', '扭矩10N·m；电压12V；序列00001234567890123456'])
def test_empty_and_unmatched_text_does_not_create_facts(raw):
    result = redact(raw)
    assert result.text == raw and not result.match_counts
    with pytest.raises(dataclasses.FrozenInstanceError): result.text = 'changed'


@pytest.mark.parametrize('values', [[True], [12], [''], ['   '], ['a\nb'], ['a\x00b'],
    ['ACME', 'acme'], ['ＡＣＭＥ', 'acme'], ['x'*101], [f'term{i}' for i in range(51)],
    ['中'*100+str(i) for i in range(40)]])
def test_invalid_terms_are_rejected_without_echoing_contents(values):
    from app.services.capa_d4_redaction import validate_terms
    with pytest.raises(ValueError) as error: validate_terms(values)
    assert str(error.value) == 'PREVIEW_INPUT_INVALID'


def test_body_budget_is_in_utf8_bytes_and_never_returns_partial_text():
    from app.services.capa_d4_redaction import redact_text
    with pytest.raises(ValueError) as error: redact_text('中' * 22000, ())
    assert str(error.value) == 'PREVIEW_SOURCE_LIMIT'
    assert redact('  ACME  ', (' ACME ',)).text == '  [指定词已遮盖]  '
