"""R7 task bindings and release evidence, stored separately from business writes."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentPfmeaImpactBinding(Base):
    __tablename__ = "agent_pfmea_impact_bindings"
    __table_args__ = (
        sa.UniqueConstraint("actor_id", "request_key", name="uq_r7_impact_actor_request"),
        sa.CheckConstraint("length(btrim(request_key)) > 0", name="ck_r7_impact_request_key"),
        sa.CheckConstraint("binding_digest ~ '^[0-9a-f]{64}$'", name="ck_r7_impact_binding_digest"),
        sa.CheckConstraint(
            "jsonb_typeof(binding) = 'object' AND octet_length(binding::text) <= 524288",
            name="ck_r7_impact_binding_shape",
        ),
    )

    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), primary_key=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False,
    )
    request_key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    binding: Mapped[dict] = mapped_column(JSONB, nullable=False)
    binding_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )


class AgentPfmeaImpactReceipt(Base):
    __tablename__ = "agent_pfmea_impact_receipts"
    __table_args__ = (
        sa.CheckConstraint("lease_epoch >= 0", name="ck_r7_impact_receipt_epoch"),
        sa.CheckConstraint(
            "kind IN ('release', 'page_confirmation', 'coverage')",
            name="ck_r7_impact_receipt_kind",
        ),
        sa.CheckConstraint("scope_digest ~ '^[0-9a-f]{64}$'", name="ck_r7_impact_scope_digest"),
        sa.CheckConstraint(
            "(page_key IS NULL OR page_key ~ '^[0-9a-f]{64}$') "
            "AND (kind <> 'page_confirmation' OR page_key IS NOT NULL) "
            "AND (kind <> 'coverage' OR page_key IS NULL)",
            name="ck_r7_impact_receipt_page",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 524288",
            name="ck_r7_impact_receipt_shape",
        ),
        sa.Index("ix_r7_impact_run_receipts", "run_id", "lease_epoch", "kind"),
        sa.Index(
            "uq_r7_impact_page_confirmation",
            "run_id", "lease_epoch", "scope_digest", "page_key",
            unique=True, postgresql_where=sa.text("kind = 'page_confirmation'"),
        ),
    )

    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_pfmea_impact_bindings.task_id"), nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False,
    )
    lease_epoch: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    scope_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    page_key: Mapped[str | None] = mapped_column(sa.String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
    )


class AgentPfmeaImpactResultReceipt(Base):
    __tablename__ = "agent_pfmea_impact_result_receipts"

    result_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_results.result_id"), primary_key=True,
    )
    receipt_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("agent_pfmea_impact_receipts.receipt_id"), primary_key=True,
    )
