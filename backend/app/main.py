import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.models.role import RoleDefinition
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
from app.api.apqp import router as apqp_router
from app.api.ppap import router as ppap_router
from app.api.shipment import router as shipment_router
from app.api.graph import router as graph_router
from app.api.admin import permissions as admin_permissions_api
from app.api.search import router as search_router
from app.api.change_impact import router as change_impact_router
from app.api.collaboration import router as collaboration_router
from app.api.mes import router as mes_router
from app.api.plm import router as plm_router
from app.api.erp import router as erp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            try:
                admin_role_result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
                admin_role = admin_role_result.scalar_one_or_none()
                if admin_role:
                    db.add(User(
                        username="admin",
                        password_hash=hash_password("Admin@2026"),
                        display_name="系统管理员",
                        role_id=admin_role.id,
                    ))
                    await db.commit()
                else:
                    print("WARNING: admin role not found in role_definitions. Run migrations and seed.")
            except Exception:
                # role_definitions table may not exist yet (migration not run)
                # Rollback failed transaction and skip admin creation
                await db.rollback()
                print("WARNING: role_definitions table not found. Run 'alembic upgrade head' and seed before using the permission system.")

    # Initialize LLM provider (non-fatal)
    from app.services.llm_provider import create_llm_provider
    try:
        app.state.llm_provider = create_llm_provider()
    except Exception as e:
        logger.warning("LLM provider init failed: %s", e)
        app.state.llm_provider = None

    # Initialize embedding provider (non-fatal)
    from app.services.embedding_provider import create_embedding_provider
    try:
        app.state.embedding_provider = create_embedding_provider()
    except Exception as e:
        logger.warning("Embedding provider init failed: %s", e)
        app.state.embedding_provider = None

    # Start collaboration session cleanup coroutine
    import asyncio
    from app.services.collaboration_service import delete_expired_sessions

    async def _cleanup_loop():
        while True:
            await asyncio.sleep(60)
            try:
                async with async_session() as db:
                    deleted = await delete_expired_sessions(db)
                    if deleted > 0:
                        logger.info("[collaboration] cleaned up %d expired sessions", deleted)
            except Exception as e:
                logger.error("[collaboration] cleanup error: %s", e)

    cleanup_task = asyncio.create_task(_cleanup_loop())

    # Start MES sync scheduler loop (every 30s)
    from app.services.mes_service import MESSyncService

    async def _mes_sync_loop():
        while True:
            await asyncio.sleep(30)
            try:
                async with async_session() as db:
                    await MESSyncService.run_sync_round(db)
            except Exception as e:
                logger.error("[mes_sync] error: %s", e)

    mes_sync_task = asyncio.create_task(_mes_sync_loop())

    # Start MES outbox processor loop (every 30s)
    from app.services.mes_service import MESPushService

    async def _mes_outbox_loop():
        while True:
            await asyncio.sleep(30)
            try:
                async with async_session() as db:
                    await MESPushService.process_outbox(db)
            except Exception as e:
                logger.error("[mes_outbox] error: %s", e)

    mes_outbox_task = asyncio.create_task(_mes_outbox_loop())

    # Start MES lifecycle cleanup loop (daily)
    from app.services.mes_service import MESLifecycleService

    async def _mes_cleanup_loop():
        while True:
            await asyncio.sleep(86400)
            try:
                async with async_session() as db:
                    stats = await MESLifecycleService.cleanup(db)
                    if any(v > 0 for v in stats.values()):
                        logger.info("[mes_lifecycle] cleanup: %s", stats)
            except Exception as e:
                logger.error("[mes_lifecycle] error: %s", e)

    mes_cleanup_task = asyncio.create_task(_mes_cleanup_loop())

    # Start PLM sync scheduler loop (every 30s)
    from app.services.plm_service import PLMSyncService

    async def _plm_sync_loop():
        while True:
            await asyncio.sleep(30)
            try:
                async with async_session() as db:
                    await PLMSyncService.run_sync_round(db)
            except Exception as e:
                logger.error("[plm_sync] error: %s", e)

    plm_sync_task = asyncio.create_task(_plm_sync_loop())

    # Start PLM change impact worker loop (every 30s)
    from app.services.plm_service import PLMChangeImpactWorker

    async def _plm_impact_loop():
        # recover_stuck_tasks and claim_tasks run in separate sessions because
        # they operate on independent state: recovery resets stuck tasks back to
        # pending, while claiming advances pending tasks to running.

        while True:
            await asyncio.sleep(30)
            try:
                # Phase 1: recover stuck + claim in separate sessions
                async with async_session() as db:
                    await PLMChangeImpactWorker.recover_stuck_tasks(db)
                    await db.commit()
                async with async_session() as db:
                    claimed = await PLMChangeImpactWorker.claim_tasks(db)
                    await db.commit()

                # Phase 2: process each claimed task — process_task() already
                # re-verifies the claim token in its own session.
                for task in claimed:
                    try:
                        async with async_session() as proc_db:
                            await PLMChangeImpactWorker.process_task(proc_db, task)
                            await proc_db.commit()
                    except Exception as e:
                        logger.error("[plm_impact] task %s error: %s", task.task_id, e)
            except Exception as e:
                logger.error("[plm_impact] error: %s", e)

    plm_impact_task = asyncio.create_task(_plm_impact_loop())

    # Start ERP sync background loop (every 60s)
    from app.services.erp_service import ERPSyncService

    async def _erp_sync_loop():
        while True:
            try:
                async with async_session() as db:
                    await ERPSyncService.sync_all(db)
            except Exception as e:
                logger.error("[erp_sync] error: %s", e)
            await asyncio.sleep(60)

    erp_sync_task = asyncio.create_task(_erp_sync_loop())

    yield

    # Cancel cleanup coroutine
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Cancel MES background tasks
    for task in (mes_sync_task, mes_outbox_task, mes_cleanup_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Cancel PLM background tasks
    for task in (plm_sync_task, plm_impact_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Cancel ERP background tasks
    for task in (erp_sync_task,):
        task.cancel()

    # Cleanup: close LLM provider httpx client if applicable
    provider = getattr(app.state, "llm_provider", None)
    if provider and hasattr(provider, "aclose"):
        await provider.aclose()
    embedding_provider = getattr(app.state, "embedding_provider", None)
    if embedding_provider and hasattr(embedding_provider, "aclose"):
        await embedding_provider.aclose()


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
app.include_router(apqp_router)
app.include_router(ppap_router)
app.include_router(shipment_router)
app.include_router(graph_router)
app.include_router(admin_permissions_api.router)
app.include_router(search_router)
app.include_router(change_impact_router)
app.include_router(collaboration_router)
app.include_router(mes_router)
app.include_router(plm_router)
app.include_router(erp_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
