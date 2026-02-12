from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, DateTime, Numeric, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin
from app.core.time import utc_now


class PriorityValueLink(Base, UUIDMixin):
    """Link between a priority revision and a value revision."""
    
    __tablename__ = "priority_value_links"
    
    priority_revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("priority_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    value_revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("value_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    
    link_weight: Mapped[Decimal] = mapped_column(
        Numeric,
        default=1.0,
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    # Relationships
    priority_revision: Mapped["PriorityRevision"] = relationship(
        "PriorityRevision",
        back_populates="value_links",
    )
    value_revision: Mapped["ValueRevision"] = relationship(
        "ValueRevision",
        back_populates="priority_links",
    )
    
    @property
    def value_id(self) -> str | None:
        """Get the value_id from the related ValueRevision."""
        return self.value_revision.value_id if self.value_revision else None
    
    __table_args__ = (
        UniqueConstraint(
            "priority_revision_id",
            "value_revision_id",
            name="uq_priority_value_link",
        ),
        Index("idx_pvl_priority_rev", "priority_revision_id"),
        Index("idx_pvl_value_rev", "value_revision_id"),
    )
