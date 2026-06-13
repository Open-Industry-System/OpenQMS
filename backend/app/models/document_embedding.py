import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entity_field: Mapped[str] = mapped_column(String(50), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding column is vector type - handled via raw SQL in migration, not mapped here
    # Queries using pgvector operators must use raw SQL or text()
    product_line_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    # "metadata" is reserved on SQLAlchemy Base — map DB column "metadata" to attribute "embedding_metadata"
    embedding_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"))
    embedding_model: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="NOW()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="NOW()")


class EmbeddingSyncOutbox(Base):
    __tablename__ = "embedding_sync_outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_line_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="'pending'")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="NOW()")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="NOW()")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
