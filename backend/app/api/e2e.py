"""E2E-only endpoints. Registered only when E2E_MODE and not production.

Provides a read-only seed-state view and a whitelist-based cleanup for test data.
Never exposed in production (gated at router registration in main.py)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.e2e_cleanup_whitelist import CLEANUP_PARENTS
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.user import User
from app.seed_e2e_constants import E2E_ACCOUNTS, E2E_KNOWN_DOCS

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.get("/seed-state")
async def get_seed_state(db: AsyncSession = Depends(get_db)):
    factories = (await db.execute(select(Factory).where(Factory.code.in_(["DC-FACT-E2E", "SH-FACT-E2E"])))).scalars().all()
    pls = (await db.execute(select(ProductLine).where(ProductLine.code == "DC-DC-100-E2E"))).scalars().all()
    users = (await db.execute(select(User).where(User.username.in_([a[0] for a in E2E_ACCOUNTS])))).scalars().all()
    roles = {r.id: r.role_key for r in (await db.execute(select(RoleDefinition))).scalars().all()}
    pw_by_user = {a[0]: a[1] for a in E2E_ACCOUNTS}  # seed_e2e is the single source of truth for passwords
    accounts = []
    for u in users:
        facs = (await db.execute(select(UserFactory.factory_id).where(UserFactory.user_id == u.user_id))).scalars().all()
        fac_codes = [f.code for f in factories if f.id in facs]
        accounts.append({
            "username": u.username,
            "password": pw_by_user.get(u.username),
            "role_key": roles.get(u.role_id),
            "factory_codes": fac_codes,
        })
    return {
        "factories": [{"code": f.code, "name": f.name, "id": str(f.id)} for f in factories],
        "product_lines": [{"code": p.code, "name": p.name, "factory_id": str(p.factory_id)} for p in pls],
        "accounts": accounts,
        "known_docs": E2E_KNOWN_DOCS,
        "used_doc_numbers": [d for ds in E2E_KNOWN_DOCS.values() for d in ds],
    }


# Version tables have BEFORE UPDATE OR DELETE triggers (prevent_version_tampering) that
# RAISE on delete (alembic 020). They would block CASCADE deletion of parent FMEAs that have
# version snapshots. In E2E_MODE (dedicated DB, workers:1) we disable them for this cleanup
# transaction, then re-enable. ALTER TABLE is transactional in PG (no implicit commit).
VERSION_TRIGGERS = [
    ("fmea_versions", "trg_fmea_version_no_update"),
    ("control_plan_versions", "trg_cp_version_no_update"),
]


@router.post("/cleanup")
async def cleanup_test_data(prefix: str = Query(..., min_length=4, max_length=20), db: AsyncSession = Depends(get_db)):
    """Whitelist-based, FK-ordered delete in a single transaction. Never string-concats table names.

    On any failure: rollback (undoes the trigger DISABLE + all deletes) and re-raise.
    Do NOT re-enable triggers in a failed/aborted transaction — that would raise a
    secondary error. ALTER TABLE is transactional, so rollback cleanly reverts the disable."""
    deleted: dict[str, int] = {}
    try:
        # Disable immutability triggers for this txn (only version tables; safe in dedicated e2e DB).
        for table, trig in VERSION_TRIGGERS:
            await db.execute(text(f'ALTER TABLE "{table}" DISABLE TRIGGER "{trig}"'))
        for model, pk_col, doc_col, children in CLEANUP_PARENTS:
            col = getattr(model, doc_col)
            pk = getattr(model, pk_col)
            parent_ids = [row[0] for row in (await db.execute(select(pk).where(col.like(f"{prefix}%")))).all()]
            if not parent_ids:
                continue
            # Delete children first by FK to parent PK.
            for child_model, fk_col in children:
                fk = getattr(child_model, fk_col)
                result = await db.execute(delete(child_model).where(fk.in_(parent_ids)))
                deleted[f"{child_model.__name__}.{fk_col}"] = deleted.get(f"{child_model.__name__}.{fk_col}", 0) + result.rowcount
            # Delete parents (CASCADE handles version/cache/change-impact rows now that triggers are disabled).
            result = await db.execute(delete(model).where(pk.in_(parent_ids)))
            deleted[f"{model.__name__}"] = result.rowcount
        # Re-enable triggers before commit (txn is still healthy here).
        for table, trig in VERSION_TRIGGERS:
            await db.execute(text(f'ALTER TABLE "{table}" ENABLE TRIGGER "{trig}"'))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"deleted": deleted}
