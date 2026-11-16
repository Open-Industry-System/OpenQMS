"""Platform-only shared login throttle state."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class PlatformLoginAttempt(PlatformBase):
    __tablename__ = "platform_login_attempts"
    __table_args__ = {"schema": "public"}

    key_kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
