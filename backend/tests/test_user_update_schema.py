"""Unit tests for UserUpdateRequest schema + password complexity helper (no DB)."""
import pytest

from app.schemas.auth import UserUpdateRequest, validate_password_complexity


def test_password_complexity_helper_accepts_strong_password():
    assert validate_password_complexity("ValidPass123!") == "ValidPass123!"


def test_password_complexity_helper_rejects_weak():
    with pytest.raises(ValueError):
        validate_password_complexity("weakpass1")


def test_user_update_request_password_optional_and_unvalidated_at_construction():
    # password absent -> no validation, None default
    req = UserUpdateRequest(display_name="X")
    assert req.password is None
    # strong password accepted
    req2 = UserUpdateRequest(password="ValidPass123!")
    assert req2.password == "ValidPass123!"
    # weak password is accepted at construction; complexity is enforced in user_service.update_user
    req3 = UserUpdateRequest(password="weakpass1")
    assert req3.password == "weakpass1"


def test_user_update_request_exclude_unset_distinguishes_null_from_absent():
    req = UserUpdateRequest(default_factory_id=None, display_name="N")
    dump = req.model_dump(exclude_unset=True)
    # default_factory_id was explicitly provided (as None) -> present
    assert "default_factory_id" in dump and dump["default_factory_id"] is None
    # role_key was not provided -> absent
    assert "role_key" not in dump


def test_user_update_request_factory_ids_defaults_none():
    req = UserUpdateRequest()
    dump = req.model_dump(exclude_unset=True)
    assert "factory_ids" not in dump
    req2 = UserUpdateRequest(factory_ids=[])
    assert req2.model_dump(exclude_unset=True)["factory_ids"] == []


def test_user_update_request_empty_email_becomes_none():
    # empty/whitespace string must not 422 on EmailStr; coerced to None pre-validation
    req = UserUpdateRequest(email="   ")
    assert req.email is None
