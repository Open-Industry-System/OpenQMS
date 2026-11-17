"""Fixture snapshots must reject the pure lane before any resource inspection."""
import pytest

from tests.ci import database_template


def test_pure_lane_refuses_database_template_before_io(monkeypatch):
    monkeypatch.setenv('OPENQMS_CI_PURE', '1')
    monkeypatch.setattr(database_template, 'verify_owned_instance',
                        lambda *_: pytest.fail('pure fixture must not inspect Docker or PostgreSQL'))
    with pytest.raises(RuntimeError, match='pure_test_database_forbidden'):
        with database_template.fixture_database({}):
            pytest.fail('pure database fixture admitted')
