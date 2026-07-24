import pytest
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate


def test_create_accepts_conclusion():
    v = VerificationCreate(root_cause_text="rc", conclusion="passed")
    assert v.conclusion == "passed"


def test_create_default_conclusion_pending():
    v = VerificationCreate(root_cause_text="rc")
    assert v.conclusion == "pending"


def test_create_rejects_is_verified_field():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", is_verified=True)  # extra='forbid' → 422


def test_create_rejects_invalid_conclusion():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", conclusion="bogus")


def test_create_rejects_invalid_method():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", method="guess")


def test_update_rejects_is_verified_field():
    with pytest.raises(Exception):
        VerificationUpdate(is_verified=True)
