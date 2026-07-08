"""审查 skill CRUD（admin 管理，按租户隔离，回退 public 全局默认）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_review_skill import AgentReviewSkill


async def get_by_name(db: AsyncSession, tenant_schema: str, name: str) -> AgentReviewSkill | None:
    """先按 (tenant, name) 查；未命中回退 (public, name)。都不中 → None。"""
    result = await db.execute(select(AgentReviewSkill).where(
        AgentReviewSkill.tenant_schema == tenant_schema,
        AgentReviewSkill.name == name,
        AgentReviewSkill.is_active.is_(True),
    ))
    skill = result.scalar_one_or_none()
    if skill is not None:
        return skill
    # 回退 public 全局默认
    result = await db.execute(select(AgentReviewSkill).where(
        AgentReviewSkill.tenant_schema == "public",
        AgentReviewSkill.name == name,
        AgentReviewSkill.is_active.is_(True),
    ))
    return result.scalar_one_or_none()


async def list_skills(db: AsyncSession, tenant_schema: str) -> list[AgentReviewSkill]:
    """列出该租户的 effective skills：tenant 自定义覆盖 public 同名 skill（按 name 去重，不返回两条）。"""
    result = await db.execute(select(AgentReviewSkill).where(
        AgentReviewSkill.tenant_schema.in_([tenant_schema, "public"]),
        AgentReviewSkill.is_active.is_(True),
    ))
    rows = list(result.scalars().all())
    # 按 name 去重：tenant 版优先于 public 版
    by_name: dict[str, AgentReviewSkill] = {}
    for r in rows:
        if r.name not in by_name or r.tenant_schema == tenant_schema:
            # tenant 版覆盖已存在的 public 版
            if r.name in by_name and by_name[r.name].tenant_schema == tenant_schema:
                continue  # 已是 tenant 版，不覆盖
            by_name[r.name] = r
    return list(by_name.values())


async def upsert(
    db: AsyncSession, tenant_schema: str, name: str, content: str, user_id
) -> AgentReviewSkill:
    """存在则更新 content + version+1；不存在则创建 version=1。"""
    result = await db.execute(select(AgentReviewSkill).where(
        AgentReviewSkill.tenant_schema == tenant_schema,
        AgentReviewSkill.name == name,
    ))
    skill = result.scalar_one_or_none()
    if skill is None:
        skill = AgentReviewSkill(
            tenant_schema=tenant_schema, name=name, content=content, version=1,
        )
        if user_id is not None:
            skill.updated_by = user_id
        db.add(skill)
    else:
        skill.content = content
        skill.version = skill.version + 1
        if user_id is not None:
            skill.updated_by = user_id
    await db.flush()
    return skill
