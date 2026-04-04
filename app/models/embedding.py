from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_types import CompatibleVector
from app.models.base import Base, UUIDMixin
from app.core.time import utc_now


class Embedding(Base, UUIDMixin):
    """Embedding vector for semantic comparison (linked to revision entity)."""
    
    __tablename__ = "embeddings"
    
    entity_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # 'value_revision' or 'priority_revision'
    
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
    )
    
    model: Mapped[str] = mapped_column(String, nullable=False)
    dims: Mapped[int] = mapped_column(Integer, nullable=False)
    
    embedding: Mapped[list[float]] = mapped_column(
        CompatibleVector(3072),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "model", name="uq_embedding_entity_model"),
        Index("idx_embeddings_entity", "entity_type", "entity_id"),
    )
