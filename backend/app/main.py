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
from app.api.audit_program import router as audit_program_router
from app.api.audit_plan import router as audit_plan_router
from app.api.audit_finding import router as audit_finding_router
from app.api.auditor import router as auditor_router
from app.api.supplier import router as supplier_router
from app.api.gauge import router as gauge_router
from app.api.msa import (
    grr_router,
    bias_router,
    linearity_router,
    stability_router,
    attribute_router,
    overview_router,
)
from app.api.special_characteristic import router as sc_router
from app.api.product_line import router as product_line_router
from app.api.management_review import router as management_review_router
from app.api.version import router as version_router
from app.api.iqc import router as iqc_router
from app.api.customer_quality import router as customer_quality_router
from app.api.scar import router as scar_router


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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.include_router(audit_program_router)
app.include_router(audit_plan_router)
app.include_router(audit_finding_router)
app.include_router(auditor_router)
app.include_router(supplier_router)
app.include_router(gauge_router)
app.include_router(grr_router)
app.include_router(bias_router)
app.include_router(linearity_router)
app.include_router(stability_router)
app.include_router(attribute_router)
app.include_router(overview_router)
app.include_router(sc_router)
app.include_router(product_line_router)
app.include_router(management_review_router)
app.include_router(version_router)
app.include_router(iqc_router)
app.include_router(customer_quality_router)
app.include_router(scar_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
