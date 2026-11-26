from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import preview_fixtures


def test_normal_seed_has_no_pr_fixture():
    assert preview_fixtures.preview_pr_from_env({}) is None


def test_preview_seed_uses_trusted_pr_number():
    assert preview_fixtures.preview_pr_from_env({
        "PREVIEW_PR": "59",
        "DATABASE_URL": "postgresql+asyncpg://qms@db/qms_preview",
    }) == 59


@pytest.mark.parametrize("pr, database", [
    ("../59", "postgresql+asyncpg://qms@db/qms_preview"),
    ("59", "postgresql+asyncpg://qms@db/qms"),
    ("59", "postgresql+asyncpg://qms@production/qms_preview"),
])
def test_invalid_identity_cannot_select_a_fixture(pr, database):
    with pytest.raises(ValueError, match="preview"):
        preview_fixtures.preview_pr_from_env({"PREVIEW_PR": pr, "DATABASE_URL": database})


async def test_only_exact_optional_fixture_runs(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value="qms_preview"))
    fixture = SimpleNamespace(seed=AsyncMock(), verify=AsyncMock())
    look_up = Mock(side_effect=lambda name: object() if name.endswith(".pr_59") else None)
    load = Mock(return_value=fixture)
    monkeypatch.setattr(preview_fixtures, "find_spec", look_up)
    monkeypatch.setattr(preview_fixtures, "import_module", load)

    await preview_fixtures.seed_preview_fixture(db, None)
    await preview_fixtures.seed_preview_fixture(db, 60)
    db.scalar.assert_not_awaited()
    load.assert_not_called()
    await preview_fixtures.seed_preview_fixture(db, 59)

    load.assert_called_once_with("app.preview_fixtures.pr_59")
    db.scalar.assert_awaited_once()
    fixture.seed.assert_awaited_once_with(db)
    fixture.verify.assert_awaited_once_with(db)


async def test_non_preview_database_rejects_fixture_before_loading(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value="qms"))
    load = Mock()
    monkeypatch.setattr(preview_fixtures, "find_spec", Mock(return_value=object()))
    monkeypatch.setattr(preview_fixtures, "import_module", load)

    with pytest.raises(ValueError, match="isolated preview database"):
        await preview_fixtures.seed_preview_fixture(db, 59)
    load.assert_not_called()


async def test_fixture_failure_propagates_to_initialization(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value="qms_preview"))
    fixture = SimpleNamespace(
        seed=AsyncMock(side_effect=RuntimeError("fixture failed")),
        verify=AsyncMock(),
    )
    monkeypatch.setattr(preview_fixtures, "find_spec", Mock(return_value=object()))
    monkeypatch.setattr(preview_fixtures, "import_module", Mock(return_value=fixture))

    with pytest.raises(RuntimeError, match="fixture failed"):
        await preview_fixtures.seed_preview_fixture(db, 59)
    fixture.verify.assert_not_awaited()


async def test_fixture_without_verification_fails_before_seeding(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value="qms_preview"))
    fixture = SimpleNamespace(seed=AsyncMock())
    monkeypatch.setattr(preview_fixtures, "find_spec", Mock(return_value=object()))
    monkeypatch.setattr(preview_fixtures, "import_module", Mock(return_value=fixture))

    with pytest.raises(ValueError, match=r"requires seed\(db\) and verify\(db\)"):
        await preview_fixtures.seed_preview_fixture(db, 59)
    fixture.seed.assert_not_awaited()


async def test_failed_verification_propagates_after_seeding(monkeypatch):
    db = SimpleNamespace(scalar=AsyncMock(return_value="qms_preview"))
    fixture = SimpleNamespace(
        seed=AsyncMock(),
        verify=AsyncMock(side_effect=ValueError("missing page data")),
    )
    monkeypatch.setattr(preview_fixtures, "find_spec", Mock(return_value=object()))
    monkeypatch.setattr(preview_fixtures, "import_module", Mock(return_value=fixture))

    with pytest.raises(ValueError, match="missing page data"):
        await preview_fixtures.seed_preview_fixture(db, 59)
    fixture.seed.assert_awaited_once_with(db)
