import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CAPAEightD(Base):
    __tablename__ = "capa_eightd"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="D1_TEAM")
    severity: Mapped[str] = mapped_column(String(20), default="general")
    d1_team: Mapped[dict] = mapped_column(JSONB, default=lambda: [])
    d2_description: Mapped[str | None] = mapped_column(Text)
    d3_interim: Mapped[str | None] = mapped_column(Text)
    d4_root_cause: Mapped[str | None] = mapped_column(Text)
    d5_correction: Mapped[str | None] = mapped_column(Text)
    d6_verification: Mapped[str | None] = mapped_column(Text)
    d7_prevention: Mapped[str | None] = mapped_column(Text)
    d8_closure: Mapped[str | None] = mapped_column(Text)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id")
    )
    fmea_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CapaRootCauseVerification(Base):
    __tablename__ = "capa_root_cause_verification"
    verification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    root_cause_text: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_attachments: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CapaAIAdoption(Base):
    __tablename__ = "capa_ai_adoption"
    adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    d_step: Mapped[str] = mapped_column(String(8), nullable=False)
    adopted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    stage_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    adopted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    adopted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CapaD7NodeAction(Base):
    __tablename__ = "capa_d7_node_action"
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # 可空：规则引擎兜底推荐无关联 FMEA（US-E2E-01 D7 兜底）
    fmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=True
    )
    failure_mode_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_cause_node_id: Mapped[str | None] = mapped_column(String(128))
    match_source: Mapped[str] = mapped_column(String(40), nullable=False)
    prevention_control_node_id: Mapped[str | None] = mapped_column(String(128))
    prevention_control_name_before: Mapped[str | None] = mapped_column(Text)
    prevention_control_name_after: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    acted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    recommendation_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # US-E2E-01.3：node-action 执行生命周期（pending→executed→verified）；本切片止于 pending
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)


class CapaPptExport(Base):
    __tablename__ = "capa_ppt_export"
    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    tenant_schema: Mapped[str | None] = mapped_column(String(63))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)  # YYYYMMDDTHHMMSSZ
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 恒 None（不落盘）
    review_status: Mapped[str] = mapped_column(String(20), default="skipped", nullable=False)
    review_rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
