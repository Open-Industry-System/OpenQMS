# backend/app/models/group_kpi_snapshot.py
import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class GroupKPISnapshot(Base):
    __tablename__ = "group_kpi_snapshots"
    __table_args__ = (
        UniqueConstraint("factory_id", "snapshot_date", name="uq_factory_snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    kpi_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)