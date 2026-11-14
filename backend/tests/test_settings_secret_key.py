import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "   ",
        "REQUIRED_GENERATED_ON_SERVER",
        " REQUIRED_GENERATED_ON_SERVER ",
        "dev-secret-key-change-in-production",
        " dev-secret-key-change-in-production ",
        "change-me-in-production",
        " change-me-in-production ",
    ],
    ids=(
        "empty",
        "whitespace",
        "placeholder",
        "wrapped-placeholder",
        "dev-default",
        "wrapped-dev-default",
        "example-placeholder",
        "wrapped-example-placeholder",
    ),
)
def test_settings_rejects_empty_placeholder_and_default_secret(secret):
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY=secret, _env_file=None)


def test_settings_accepts_non_default_test_secret():
    settings = Settings(SECRET_KEY="fixed-non-production-test-secret", _env_file=None)

    assert settings.SECRET_KEY == "fixed-non-production-test-secret"
