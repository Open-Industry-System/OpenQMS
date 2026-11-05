"""Admin API for runtime AI configuration."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from app.core.permissions import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.ai_config import (
    AIConfigOut,
    AIConfigTestResultSchema,
    AIConfigUpdate,
    ProviderTestResultSchema,
)
from app.services import ai_config_service

router = APIRouter(prefix="/api/admin", tags=["admin-ai-config"])


def _require_single_tenant_ai_config() -> None:
    if settings.TENANT_MODE != "single":
        raise HTTPException(status_code=503, detail="Global AI configuration unavailable in multi-tenant mode")


@router.get("/ai-config", response_model=AIConfigOut)
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return the current AI / LLM configuration with the API key masked."""
    _require_single_tenant_ai_config()
    return await ai_config_service.get_ai_config(db)


@router.put("/ai-config", response_model=AIConfigOut)
async def update_ai_config(
    req: AIConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Update AI / LLM configuration and recreate providers."""
    _require_single_tenant_ai_config()
    return await ai_config_service.update_ai_config(db, req, user.user_id, request.app.state)


@router.post("/ai-config/test", response_model=AIConfigTestResultSchema)
async def test_ai_config(
    req: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Probe LLM and embedding providers using the submitted config (no persistence)."""
    _require_single_tenant_ai_config()
    result = await ai_config_service.test_ai_config(db, req)
    return AIConfigTestResultSchema(
        llm=ProviderTestResultSchema(
            ok=result.llm.ok,
            latency_ms=result.llm.latency_ms,
            detail=result.llm.detail,
        ),
        embedding=ProviderTestResultSchema(
            ok=result.embedding.ok,
            latency_ms=result.embedding.latency_ms,
            detail=result.embedding.detail,
        ),
    )
