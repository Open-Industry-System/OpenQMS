import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RoleDefinition(Base):
    __tablename__ = "role_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(50), nullable=False)
    name_en: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    bypass_row_level_security: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "module", name="uq_role_module"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("role_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    permission_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    role: Mapped["RoleDefinition"] = relationship(back_populates="permissions")


class UserProductLine(Base):
    __tablename__ = "user_product_lines"
    __table_args__ = (
        UniqueConstraint("user_id", "product_line_code", name="uq_user_product_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_line_code: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("product_lines.code", ondelete="CASCADE"),
        nullable=False,
    )
