from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentPluginInstallation(Base):
    """Tenant-local plugin installation metadata; plugin delivery is out of scope."""

    __tablename__ = "agent_plugin_installations"
    __table_args__ = (
        UniqueConstraint("plugin_key", "plugin_version"),
    )

    installation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    plugin_key: Mapped[str] = mapped_column(String(100), nullable=False)
    plugin_version: Mapped[str] = mapped_column(String(40), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    credential_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentPluginGrant(Base):
    """Tenant-local capability grant metadata, disabled unless later explicitly enabled."""

    __tablename__ = "agent_plugin_grants"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(factory_ids) = 'array' AND jsonb_array_length(factory_ids) > 0",
            name="ck_agent_plugin_grant_factory_ids_nonempty",
        ),
    )

    grant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_plugin_installations.installation_id"),
        nullable=False,
    )
    capability_id: Mapped[str] = mapped_column(String(160), nullable=False)
    factory_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    product_line_codes: Mapped[list[str] | None] = mapped_column(JSONB)
    object_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    granted_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
