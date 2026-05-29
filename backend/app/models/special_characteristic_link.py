import uuid

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SpecialCharacteristicLink(Base):
    __tablename__ = "special_characteristic_links"
    __table_args__ = (
        UniqueConstraint(
            "sc_id", "source_type", "source_id", "source_item_id",
            name="uq_sc_link",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("special_characteristics.sc_id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
