from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.core.security import hash_password
from app.api.auth import router as auth_router
from app.api.fmea import router as fmea_router
from app.api.capa import router as capa_router
from app.api.dashboard import router as dashboard_router
from app.api.quality_goal import router as quality_goal_router
from app.api.control_plan import router as control_plan_router
from app.api.spc import router as spc_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            db.add(User(
                username="admin",
                password_hash=hash_password("Admin@2026"),
                display_name="系统管理员",
                role="admin",
            ))
            await db.commit()
    yield


app = FastAPI(title="OpenQMS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(fmea_router)
app.include_router(capa_router)
app.include_router(dashboard_router)
app.include_router(quality_goal_router)
app.include_router(control_plan_router)
app.include_router(spc_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
