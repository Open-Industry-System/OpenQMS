import pytest
from app.services import agent_review_skill_service

pytestmark = pytest.mark.requires_db


async def test_get_by_name_fallback_to_public(db):
    """tenant A 未自定义 → 回退 public 全局默认（seed）。"""
    skill = await agent_review_skill_service.get_by_name(db, "tenant_a", "capa_ppt_review")
    assert skill is not None
    assert skill.tenant_schema == "public"
    assert skill.name == "capa_ppt_review"


async def test_get_by_name_tenant_specific_wins(db):
    """tenant 自定义 skill 优先于 public 回退。"""
    await agent_review_skill_service.upsert(db, "tenant_a", "capa_ppt_review", "tenant A content", None)
    skill = await agent_review_skill_service.get_by_name(db, "tenant_a", "capa_ppt_review")
    assert skill is not None
    assert skill.tenant_schema == "tenant_a"
    assert skill.content == "tenant A content"


async def test_upsert_new_version_increments(db):
    """upsert 已存在 → version+1；新建 → version=1。"""
    s1 = await agent_review_skill_service.upsert(db, "tenant_b", "capa_ppt_review", "v1 content", None)
    assert s1.version == 1
    s2 = await agent_review_skill_service.upsert(db, "tenant_b", "capa_ppt_review", "v2 content", None)
    assert s2.version == 2
    assert s2.content == "v2 content"


async def test_get_by_name_not_found(db):
    """不存在的 skill name → None（即使回退也只回退 capa_ppt_review）。"""
    skill = await agent_review_skill_service.get_by_name(db, "tenant_a", "nonexistent_skill")
    assert skill is None


async def test_list_skills_returns_public_default(db):
    """无自定义时 list 返回 public 默认（仅 1 条，不重复）。"""
    skills = await agent_review_skill_service.list_skills(db, "tenant_c")
    names = [s.name for s in skills]
    assert "capa_ppt_review" in names
    # 无自定义时只有 public 那一条，不应重复
    assert names.count("capa_ppt_review") == 1


async def test_list_skills_tenant_overrides_public_no_dup(db):
    """租户自定义后 list 只返回租户那条（tenant 覆盖 public，不出现两条同名）。"""
    await agent_review_skill_service.upsert(db, "tenant_a", "capa_ppt_review", "tenant A content", None)
    skills = await agent_review_skill_service.list_skills(db, "tenant_a")
    names = [s.name for s in skills]
    assert names.count("capa_ppt_review") == 1
    assert skills[0].tenant_schema == "tenant_a"
