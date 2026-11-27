"""Tenant-local IQC task bindings and released source snapshots."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcInvestigationBinding(Base):
    __tablename__ = "agent_iqc_investigation_bindings"
    __table_args__ = (
        sa.CheckConstraint("binding_digest ~ '^[0-9a-f]{64}$'", name="ck_iqc_binding_digest"),
        sa.CheckConstraint(
            "jsonb_typeof(binding) = 'object' AND octet_length(binding::text) <= 16384",
            name="ck_iqc_binding_shape",
        ),
    )

    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), primary_key=True,
    )
    binding: Mapped[dict] = mapped_column(JSONB, nullable=False)
    binding_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )


class IqcInvestigationReceipt(Base):
    __tablename__ = "agent_iqc_investigation_receipts"
    __table_args__ = (
        sa.CheckConstraint("lease_epoch >= 0", name="ck_iqc_receipt_epoch"),
        sa.CheckConstraint("kind IN ('source', 'model_attempt')", name="ck_iqc_receipt_kind"),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 524288",
            name="ck_iqc_receipt_shape",
        ),
        sa.Index("ix_iqc_investigation_run_receipts", "run_id", "lease_epoch"),
    )

    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_iqc_investigation_bindings.task_id"), nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False,
    )
    lease_epoch: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )
