"""Synthetic SCAR cases for the PR 59 supply-chain risk acceptance plan."""

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, UserProductLine
from app.models.supplier import Supplier, SupplierSCAR
from app.models.user import User

LINE_A = "PR59-A"
LINE_B = "PR59-B"
LINE_SUPPLIER = "PR59-SCAR-LINES"
MONTH_END_SUPPLIER = "PR59-SCAR-EOM"
NEXT_MONTH_SUPPLIER = "PR59-SCAR-NEXT"

SUPPLIERS = {
    LINE_SUPPLIER: "PR59 产线计数样本",
    MONTH_END_SUPPLIER: "PR59 月末当天关闭",
    NEXT_MONTH_SUPPLIER: "PR59 次月首日关闭",
}


async def seed(db: AsyncSession) -> None:
    """Add the cases to the seeded Manager's factory without resetting existing rows."""
    manager = (
        await db.execute(
            select(User.user_id, User.factory_id)
            .join(RoleDefinition, User.role_id == RoleDefinition.id)
            .where(User.username == "manager", RoleDefinition.role_key == "manager")
        )
    ).one()
    if manager.factory_id is None:
        raise ValueError("PR 59 preview fixture requires a seeded Manager factory")

    for code, name in ((LINE_A, "PR59 验收产线 A"), (LINE_B, "PR59 验收产线 B")):
        await db.execute(
            insert(ProductLine)
            .values(code=code, name=name, factory_id=manager.factory_id, is_active=True)
            .on_conflict_do_nothing(index_elements=[ProductLine.code])
        )
        line_factory = await db.scalar(select(ProductLine.factory_id).where(ProductLine.code == code))
        if line_factory != manager.factory_id:
            raise ValueError(f"PR 59 preview line {code} is already assigned to another factory")
        await db.execute(
            insert(UserProductLine)
            .values(user_id=manager.user_id, product_line_code=code)
            .on_conflict_do_nothing(
                index_elements=[UserProductLine.user_id, UserProductLine.product_line_code]
            )
        )

    supplier_ids = {}
    for supplier_no, name in SUPPLIERS.items():
        await db.execute(
            insert(Supplier)
            .values(
                supplier_no=supplier_no,
                name=name,
                short_name=name,
                factory_id=manager.factory_id,
                created_by=manager.user_id,
                status="approved",
            )
            .on_conflict_do_nothing(index_elements=[Supplier.factory_id, Supplier.supplier_no])
        )
        supplier_ids[supplier_no] = await db.scalar(
            select(Supplier.supplier_id).where(
                Supplier.factory_id == manager.factory_id, Supplier.supplier_no == supplier_no
            )
        )

    issued = date.today().replace(day=1)
    month_end = issued.replace(day=monthrange(issued.year, issued.month)[1])
    next_month = month_end + timedelta(days=1)
    cases = (
        ("PR59-LINE-A-01", LINE_SUPPLIER, LINE_A, None, "产线 A 的开放 SCAR"),
        ("PR59-LINE-B-01", LINE_SUPPLIER, LINE_B, None, "产线 B 的第 1 条开放 SCAR"),
        ("PR59-LINE-B-02", LINE_SUPPLIER, LINE_B, None, "产线 B 的第 2 条开放 SCAR"),
        ("PR59-MONTH-END", MONTH_END_SUPPLIER, LINE_A, month_end, "月末当天已关闭"),
        ("PR59-NEXT-MONTH", NEXT_MONTH_SUPPLIER, LINE_A, next_month, "次月首日才关闭"),
    )
    await db.execute(
        insert(SupplierSCAR)
        .values([
            {
                "scar_no": scar_no,
                "supplier_id": supplier_ids[supplier_no],
                "factory_id": manager.factory_id,
                "product_line_code": line,
                "source_type": "internal",
                "description": f"PR59 合成验收样本：{description}",
                "issued_by": manager.user_id,
                "issued_date": issued,
                "closed_date": closed,
                "status": "closed" if closed else "open",
            }
            for scar_no, supplier_no, line, closed, description in cases
        ])
        .on_conflict_do_nothing(index_elements=[SupplierSCAR.scar_no])
    )
