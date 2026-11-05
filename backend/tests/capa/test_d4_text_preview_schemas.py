from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
import pytest

REPORT = UUID('00000000-0000-0000-0000-000000000001')


def types():
    from app.schemas import capa_d4_text_preview
    return capa_d4_text_preview


@pytest.mark.parametrize('value', [{'replacement_terms': [True]}, {'replacement_terms': ['']},
    {'replacement_terms': ['x'*101]}, {'replacement_terms': ['a', 'A']},
    {'replacement_terms': ['a'], 'data_class': 'internal'}, {'replacement_terms': [], 'schema': 'public'},
    {'replacement_terms': [], 'source_version': 'f'*64}, {'replacement_terms': None}])
def test_request_rejects_invalid_terms_and_client_authority(value):
    with pytest.raises(ValidationError): types().D4PreviewRequest.model_validate(value)


def test_response_enforces_restricted_candidate_and_fixed_field_set():
    mod = types()
    field = mod.D4PreviewField(field='d4_root_cause', verification_id=None,
        redacted_text='技术描述', source_status='unverified', source_ref=None, match_counts={})
    now = datetime(2030, 1, 1, tzinfo=UTC)
    output = mod.D4TextPreview(report_id=REPORT, rule_version='capa.d4.redaction.v1', source_version='a'*64,
        generated_at=now, expires_at=now+timedelta(seconds=30), fields=[field])
    assert output.data_class == 'restricted' and output.projection == 'redaction_candidate'
    assert output.declassification_status == 'not_approved' and output.external_delivery_allowed is False
    for change in ({'data_class': 'internal'}, {'external_delivery_allowed': True}, {'declassification_status': 'approved'},
            {'source_version': 'short'}, {'expires_at': now-timedelta(seconds=1)}, {'untrusted': True}):
        with pytest.raises(ValidationError):
            mod.D4TextPreview.model_validate({**output.model_dump(), **change})
    for change in ({'field': 'd2_description'}, {'match_counts': {'raw_word': 1}}, {'match_counts': {'literal': True}},
            {'match_counts': {'literal': -1}}, {'raw_text': 'SECRET'}):
        with pytest.raises(ValidationError): mod.D4PreviewField.model_validate({**field.model_dump(), **change})


def test_terms_are_normalized_in_memory_without_exposing_raw_values_in_repr():
    request = types().D4PreviewRequest(replacement_terms=[' ACME '])
    assert request.replacement_terms == ['ACME']
    assert 'ACME' not in repr(request)
