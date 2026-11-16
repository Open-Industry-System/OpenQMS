# backend/tests/test_capa_draft_schema.py
import uuid
import pytest
from app.schemas.capa_draft import DraftRequest


def test_draft_request_extra_forbid():
    with pytest.raises(ValueError):
        DraftRequest(format="structured", request_id=str(uuid.uuid4()), extra_field="bad")
