import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupplyChainRiskSnapshot(Base):
    __tablename__ = "supply_chain_risk_snapshots"
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_line_code", "snapshot_period", name="uq_supplier_pl_period"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("product_lines.code", ondelete="CASCADE"), nullable=True)
    snapshot_period: Mapped[str] = mapped_column(String(7), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, server_default="low")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    delivery_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    compliance_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    erp_on_time_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    erp_on_time_rate_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    purchase_amount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delivery_delay_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_scar_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ppm_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
