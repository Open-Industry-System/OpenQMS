import pytest
from fastapi import HTTPException

from app.api import auth


def setup_function():
    auth._login_attempts.clear()


def test_different_clients_have_independent_login_budgets():
    for _ in range(auth._LOGIN_RATE_LIMIT):
        auth._check_login_rate_limit("198.51.100.10")

    with pytest.raises(HTTPException) as exc:
        auth._check_login_rate_limit("198.51.100.10")
    assert exc.value.status_code == 429

    auth._check_login_rate_limit("198.51.100.11")
    assert len(auth._login_attempts["198.51.100.11"]) == 1


def test_login_attempts_expire_after_rate_limit_window(monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1_000.0)
    for _ in range(auth._LOGIN_RATE_LIMIT):
        auth._check_login_rate_limit("198.51.100.10")

    monkeypatch.setattr(
        auth.time, "time", lambda: 1_000.0 + auth._LOGIN_RATE_WINDOW
    )
    auth._check_login_rate_limit("198.51.100.10")

    assert len(auth._login_attempts["198.51.100.10"]) == 1
