# backend/tests/test_capa_draft_schema.py
import uuid
import pytest
from app.schemas.capa_draft import DraftRequest, DraftResponse, ParagraphLLMOutput


def test_draft_request_extra_forbid():
    with pytest.raises(ValueError):
        DraftRequest(format="structured", request_id=str(uuid.uuid4()), extra_field="bad")


def test_draft_response_fields():
    resp = DraftResponse(content="test", structured_data=None, request_id=uuid.uuid4(), step="d2")
    assert resp.step == "d2"


def test_paragraph_llm_output():
    out = ParagraphLLMOutput(content="段落内容")
    assert out.content == "段落内容"
