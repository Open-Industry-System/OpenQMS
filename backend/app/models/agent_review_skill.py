"""审查 skill 模型（admin 管理，按租户隔离，回退 public 全局默认）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentReviewSkill(Base):
    __tablename__ = "agent_review_skill"
    skill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_schema: Mapped[str | None] = mapped_column(String(63))  # 'public' = 全局默认（seed）
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 固定 "capa_ppt_review"
    content: Mapped[str] = mapped_column(Text, nullable=False)      # 审查标准（admin 可改）
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 唯一性由迁移中的 COALESCE 表达式唯一索引保证（NULL != NULL 会漏防 UniqueConstraint）
