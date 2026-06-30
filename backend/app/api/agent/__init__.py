from fastapi import APIRouter

from app.api.agent import actions, messages, sessions, whitelist

router = APIRouter(prefix="/api/agent", tags=["agent"])
router.include_router(sessions.router)
router.include_router(messages.router)
router.include_router(actions.router)
router.include_router(whitelist.router)
