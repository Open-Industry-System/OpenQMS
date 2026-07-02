"""E2E-only endpoints. Registered only when E2E_MODE and not production.

Provides a read-only seed-state view and a whitelist-based cleanup for test data.
Never exposed in production (gated at router registration in main.py)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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


@router.post("/cleanup")
async def cleanup_test_data(prefix: str = Query(..., min_length=4, max_length=20), db: AsyncSession = Depends(get_db)):
    """Delete test data whose doc_no/name starts with `prefix` (e.g. E2E-M1).
    Whitelist-based, FK-ordered, single transaction. Implemented in Task 4."""
    # Implemented in Task 4.
    raise NotImplementedError
