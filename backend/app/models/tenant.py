import uuid
from datetime import datetime

from sqlalchemy import String, BigInteger, Integer, Text, DateTime, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped

from app.database import PlatformBase


class Tenant(PlatformBase):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
            name="ck_tenant_slug_format",
        ),
        CheckConstraint(
            "schema_name ~ '^tenant_[a-z0-9_]{1,56}$'",
            name="ck_tenant_schema_name_format",
        ),
        CheckConstraint(
            "subdomain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
            name="ck_tenant_subdomain_format",
        ),
        Index("ix_tenants_subdomain", "subdomain"),
        Index("ix_tenants_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    subdomain: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provisioning_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provisioning_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    db_instance: Mapped[str | None] = mapped_column(String(100), nullable=True)
    db_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    user_count: Mapped[int] = mapped_column(Integer, default=0)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )