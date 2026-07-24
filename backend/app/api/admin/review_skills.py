"""Admin API for review skill management (US-E2E-01.10)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_admin
from app.core.tenant import tenant_schema
from app.database import get_db
from app.models.user import User
from app.schemas.agent_review_skill import ReviewSkillResponse, ReviewSkillUpsert
from app.services import agent_review_skill_service

router = APIRouter(prefix="/api/admin/review-skills", tags=["admin-review-skills"])


def _to_response(skill) -> ReviewSkillResponse:
    return ReviewSkillResponse(
        skill_id=str(skill.skill_id),
        tenant_schema=skill.tenant_schema,
        name=skill.name,
        content=skill.content,
        version=skill.version,
        is_active=skill.is_active,
    )


@router.get("", response_model=list[ReviewSkillResponse])
async def list_review_skills(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    return [_to_response(s) for s in await agent_review_skill_service.list_skills(db, tenant_schema(request))]


@router.get("/{name}", response_model=ReviewSkillResponse)
async def get_review_skill(
    name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    if name != "capa_ppt_review":
        raise HTTPException(404, "不支持的审查 skill")
    skill = await agent_review_skill_service.get_by_name(db, tenant_schema(request), name)
    if skill is None:
        raise HTTPException(404, "审查 skill 不存在")
    return _to_response(skill)


@router.put("/{name}", response_model=ReviewSkillResponse)
async def upsert_review_skill(
    name: str,
    body: ReviewSkillUpsert,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    if name != "capa_ppt_review":
        raise HTTPException(404, "不支持的审查 skill（本切片固定 capa_ppt_review）")
    if not body.content or not body.content.strip():
        raise HTTPException(400, "审查标准不可为空")
    skill = await agent_review_skill_service.upsert(
        db, tenant_schema(request), name, body.content, user.user_id,
    )
    await db.commit()
    return _to_response(skill)
