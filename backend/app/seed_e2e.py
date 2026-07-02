"""Deterministic idempotent E2E seed. Run: python -m app.seed_e2e

Idempotent: safe to re-run. Uses -E2E- infix doc numbers so cleanup never touches seed."""
import asyncio
import uuid

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import async_session
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.product_type import ProductType  # noqa: F401 — registers product_types for FK resolution
from app.models.role import RoleDefinition
from app.models.user import User
from app.seed_e2e_constants import (
    E2E_ACCOUNTS, E2E_FACTORY_DC100, E2E_FACTORY_SH, E2E_PRODUCT_LINE,
)

# Fixed UUIDs for idempotency
FACT_DC100_ID = uuid.UUID("00000000-0000-0000-0000-000000e20001")
FACT_SH_ID = uuid.UUID("00000000-0000-0000-0000-000000e20002")
PFMEA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20100")
CAPA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20200")


async def _seed_factories(db) -> dict:
    factories = {}
    for code, name, location, fid in [
        (E2E_FACTORY_DC100["code"], E2E_FACTORY_DC100["name"], E2E_FACTORY_DC100["location"], FACT_DC100_ID),
        (E2E_FACTORY_SH["code"], E2E_FACTORY_SH["name"], E2E_FACTORY_SH["location"], FACT_SH_ID),
    ]:
        existing = (await db.execute(select(Factory).where(Factory.code == code))).scalar_one_or_none()
        if not existing:
            db.add(Factory(id=fid, code=code, name=name, location=location, is_active=True))
            await db.flush()
            factories[code] = fid
        else:
            factories[code] = existing.id
    return factories


async def _seed_product_line(db, factory_ids):
    code = E2E_PRODUCT_LINE["code"]
    existing = (await db.execute(select(ProductLine).where(ProductLine.code == code))).scalar_one_or_none()
    if not existing:
        db.add(ProductLine(
            code=code, name=E2E_PRODUCT_LINE["name"], is_active=True,
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            product_type_code=E2E_PRODUCT_LINE["product_type_code"],
        ))
        await db.flush()


async def _seed_accounts(db, factory_ids):
    roles = {r.role_key: r.id for r in (await db.execute(select(RoleDefinition))).scalars().all()}
    # Non-bypass roles need a UserProductLine assignment or resolve_product_line_scope
    # returns ProductLineScope.NONE → no FMEA/CAPA data visible (factory_scope.py:56).
    # admin/groupadmin have bypass_row_level_security → ProductLineScope.ALL, no assignment needed.
    NON_BYPASS_USERNAMES = {"engineer", "manager", "viewer"}
    for username, password, role_key, factory_codes in E2E_ACCOUNTS:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            user = User(
                username=username, display_name=username,
                password_hash=hash_password(password), role_id=roles[role_key], is_active=True,
                legacy_role=role_key,
            )
            db.add(user)
            await db.flush()
        # Ensure factory assignments
        existing_facs = {f.factory_id for f in (
            await db.execute(select(UserFactory).where(UserFactory.user_id == user.user_id))
        ).scalars().all()}
        for code in factory_codes:
            fid = factory_ids[code]
            if fid not in existing_facs:
                db.add(UserFactory(user_id=user.user_id, factory_id=fid))
        # Ensure product-line assignment for non-bypass users (so they see FMEA/CAPA data)
        if username in NON_BYPASS_USERNAMES:
            from app.models.role import UserProductLine
            existing_pls = {
                p.product_line_code for p in (
                    await db.execute(select(UserProductLine).where(UserProductLine.user_id == user.user_id))
                ).scalars().all()
            }
            if E2E_PRODUCT_LINE["code"] not in existing_pls:
                db.add(UserProductLine(user_id=user.user_id, product_line_code=E2E_PRODUCT_LINE["code"]))


async def _seed_known_docs(db, factory_ids):
    """Create one known PFMEA + one known CAPA for read-flow assertions.

    Model columns verified in app/models/fmea.py and app/models/capa.py:
    - FMEADocument: pk=fmea_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (fmea_type, product_line_code, status, version, …).
    - CAPAEightD: pk=report_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (status='D1_TEAM', severity, …).
    """
    from app.models.fmea import FMEADocument
    from app.models.capa import CAPAEightD

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()

    pfmea = (await db.execute(select(FMEADocument).where(FMEADocument.document_no == "PFMEA-E2E-001"))).scalar_one_or_none()
    if not pfmea:
        db.add(FMEADocument(
            fmea_id=PFMEA_E2E_ID,
            document_no="PFMEA-E2E-001",
            title="E2E 已知 PFMEA",
            fmea_type="PFMEA",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            status="draft",
            created_by=admin.user_id,
        ))

    capa = (await db.execute(select(CAPAEightD).where(CAPAEightD.document_no == "8D-E2E-001"))).scalar_one_or_none()
    if not capa:
        db.add(CAPAEightD(
            report_id=CAPA_E2E_ID,
            document_no="8D-E2E-001",
            title="E2E 已知 8D",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            created_by=admin.user_id,
        ))


async def main():
    async with async_session() as db:
        factory_ids = await _seed_factories(db)
        await _seed_product_line(db, factory_ids)
        await _seed_accounts(db, factory_ids)
        await _seed_known_docs(db, factory_ids)
        await db.commit()
    print("E2E seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
