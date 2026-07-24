import pytest
from sqlalchemy import text

pytestmark = pytest.mark.requires_db


async def test_migration_creates_both_tables_and_seeds_skill(db):
    """After upgrade, both tables exist + capa_ppt_review skill seeded with tenant_schema='public'."""
    # to_regclass 返回表名（存在）或 NULL（不存在）--不依赖 sync_engine/inspect
    capappt = (await db.execute(text("SELECT to_regclass('capa_ppt_export')"))).scalar()
    skill = (await db.execute(text("SELECT to_regclass('agent_review_skill')"))).scalar()
    assert capappt == "capa_ppt_export"
    assert skill == "agent_review_skill"
    # seed
    row = (await db.execute(text(
        "SELECT name, tenant_schema, version, is_active FROM agent_review_skill WHERE name='capa_ppt_review'"
    ))).fetchone()
    assert row is not None
    assert row.name == "capa_ppt_review"
    assert row.tenant_schema == "public"
    assert row.version == 1
    assert row.is_active is True
