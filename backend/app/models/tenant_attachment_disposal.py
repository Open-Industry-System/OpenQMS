"""Platform-authorized disposal records for obsolete attachment namespaces."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class TenantAttachmentStorageDisposal(PlatformBase):
    __tablename__ = "tenant_attachment_storage_disposals"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "origin_generation",
            "storage_namespace",
            name="uq_tenant_attachment_disposal_namespace",
        ),
        sa.CheckConstraint(
            "reason IN ('test_rebuild','tenant_destroyed')",
            name="ck_tenant_attachment_disposal_reason",
        ),
    )

    disposal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    origin_generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    storage_namespace: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    maintenance_attempt_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
