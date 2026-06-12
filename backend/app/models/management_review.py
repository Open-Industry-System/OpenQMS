import uuid
from datetime import datetime

from sqlalchemy import String, Date, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, deferred

from app.database import Base


class ManagementReview(Base):
    __tablename__ = "management_reviews"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    review_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    actual_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )
    report_status: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False
    )
    generated_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)
    product_line_code: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("product_lines.code", ondelete="SET NULL"),
        nullable=True,
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chair_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    participants: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)
    meeting_minutes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_package: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)
    manual_inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)
    attachments: Mapped[dict | None] = mapped_column(JSONB, nullable=True, deferred=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    chair_person = relationship("User", foreign_keys=[chair_person_id])
    creator = relationship("User", foreign_keys=[created_by])
    outputs = relationship(
        "ReviewOutput", back_populates="review", cascade="all, delete-orphan"
    )
    reports = relationship(
        "ReviewReport",
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ReviewReport.version_no.desc()",
        lazy="select",
    )


class ReviewOutput(Base):
    __tablename__ = "review_outputs"

    output_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("management_reviews.review_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    review = relationship("ManagementReview", back_populates="outputs")
    responsible = relationship("User", foreign_keys=[responsible_id])
    verifier = relationship("User", foreign_keys=[verified_by])
