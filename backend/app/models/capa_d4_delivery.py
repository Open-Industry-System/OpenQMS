"""Tenant-local D4 delivery metadata, without body or implicit authorization."""
from datetime import datetime
from uuid import UUID as PyUUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import TenantBase


class CapaD4RootCauseRevision(TenantBase):
    __tablename__ = 'capa_d4_root_cause_revisions'
    __table_args__ = (
        sa.PrimaryKeyConstraint('revision_id', name='pk_d4_revision'),
        sa.CheckConstraint('revision_no >= 0', name='ck_d4_revision_no'),
        sa.CheckConstraint("field_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_revision_field_hmac'),
        sa.UniqueConstraint('report_id', 'revision_no', name='uq_d4_revision_report_no'),
    )
    revision_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    report_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_d4_revision_report_id'), nullable=False)
    revision_no: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    field_hmac: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_d4_revision_actor_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    write_path: Mapped[str] = mapped_column(sa.String(40), nullable=False)


class CapaD4RootCauseSourceProof(TenantBase):
    __tablename__ = 'capa_d4_root_cause_source_proofs'
    __table_args__ = (
        sa.PrimaryKeyConstraint('proof_id', name='pk_d4_proof'),
        sa.CheckConstraint("verification_version ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_verification_version'),
        sa.CheckConstraint("node_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_node_hmac'),
        sa.CheckConstraint("field_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_field_hmac'),
        sa.CheckConstraint('tenant_generation >= 0', name='ck_d4_proof_generation'),
        sa.CheckConstraint("declaration_kind = 'employee_declared_complete_v1'", name='ck_d4_proof_declaration'),
        sa.CheckConstraint("status IN ('active','superseded')", name='ck_d4_proof_status'),
        sa.Index('uq_d4_proof_active_revision', 'report_id', 'revision_id', unique=True, postgresql_where=sa.text("status = 'active'")),
    )
    proof_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    report_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_d4_proof_report_id'), nullable=False)
    revision_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_revisions.revision_id', ondelete="RESTRICT", name='fk_d4_proof_revision_id'), nullable=False)
    verification_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_root_cause_verification.verification_id', ondelete="RESTRICT", name='fk_d4_proof_verification_id'), nullable=False)
    verification_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    tenant_generation: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    factory_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('factories.id', ondelete="RESTRICT", name='fk_d4_proof_factory_id'), nullable=False)
    product_line_code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source_projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    fmea_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cause_node_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    node_hmac: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    field_hmac: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    declaration_kind: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    superseded_by: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_d4_proof_actor_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class AgentRestrictedProjectionReceipt(TenantBase):
    __tablename__ = 'agent_restricted_projection_receipts'
    __table_args__ = (
        sa.PrimaryKeyConstraint('receipt_id', name='pk_restricted_receipt'),
        sa.CheckConstraint('lease_epoch >= 0', name='ck_restricted_receipt_epoch'),
        sa.CheckConstraint('tenant_generation >= 0', name='ck_restricted_receipt_generation'),
        sa.CheckConstraint("projection_digest ~ '^[0-9a-f]{64}$'", name='ck_restricted_receipt_projection_digest'),
        sa.CheckConstraint("projection_id = 'capa.d4.root_cause_candidate.masked.v1'", name='ck_restricted_receipt_projection'),
        sa.CheckConstraint("data_class = 'restricted'", name='ck_restricted_receipt_class'),
    )
    receipt_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    task_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete="RESTRICT", name='fk_restricted_receipt_task_id'), nullable=False)
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete="RESTRICT", name='fk_restricted_receipt_run_id'), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    tenant_generation: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    source_capa_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_restricted_receipt_source_capa_id'), nullable=False)
    projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    projection_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    data_class: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
