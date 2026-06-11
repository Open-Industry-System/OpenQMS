import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlConfig(Base):
    __tablename__ = "iqc_aql_configs"
    __table_args__ = (
        UniqueConstraint("config_key", "product_line_code", name="uq_config_key_product_line"),
        # Note: partial indexes for NULL product_line_code created in migration
    )

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key: Mapped[str] = mapped_column(String(50), nullable=False)
    config_value: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
