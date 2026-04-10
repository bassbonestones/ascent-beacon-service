from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Literal, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.task_completion import TaskCompletion
    from app.models.user import User


# Type aliases for Literal types
DependencyStrength = Literal["hard", "soft"]
DependencyScope = Literal["all_occurrences", "next_occurrence", "within_window"]
ResolutionSource = Literal["manual", "chain", "override", "system"]
ReadinessState = Literal["ready", "blocked", "partial", "advisory"]


class DependencyRule(Base, UUIDMixin, TimestampMixin):
    """Defines a dependency relationship between two tasks."""

    __tablename__ = "dependency_rules"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    upstream_task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    downstream_task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Strength: 'hard' (blocks) or 'soft' (warning only)
    strength: Mapped[str] = mapped_column(String(10), nullable=False, default="soft")

    # Scope: how do occurrences relate?
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="next_occurrence"
    )

    # Count: how many upstream completions required (e.g., 4 waters before gym)
    required_occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    # Window: for 'within_window' scope, validity duration in minutes
    # NULL = use upstream task's recurrence interval as default
    validity_window_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="dependency_rules")
    upstream_task: Mapped["Task"] = relationship(
        foreign_keys=[upstream_task_id],
        back_populates="downstream_dependency_rules",
    )
    downstream_task: Mapped["Task"] = relationship(
        foreign_keys=[downstream_task_id],
        back_populates="upstream_dependency_rules",
    )
    resolutions: Mapped[List["DependencyResolution"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # One rule per upstream-downstream pair
        UniqueConstraint(
            "upstream_task_id", "downstream_task_id", name="uq_dependency_rule_pair"
        ),
        CheckConstraint(
            "upstream_task_id != downstream_task_id", name="check_no_self_dependency"
        ),
        CheckConstraint(
            "strength IN ('hard', 'soft')", name="check_strength_values"
        ),
        CheckConstraint(
            "scope IN ('all_occurrences', 'next_occurrence', 'within_window')",
            name="check_scope_values",
        ),
        CheckConstraint("required_occurrence_count >= 1", name="check_min_count"),
        Index("idx_dependency_rules_user", "user_id"),
        Index("idx_dependency_rules_upstream", "upstream_task_id"),
        Index("idx_dependency_rules_downstream", "downstream_task_id"),
    )

    @property
    def is_hard(self) -> bool:
        """Check if this is a hard (blocking) dependency."""
        return self.strength == "hard"

    @property
    def is_soft(self) -> bool:
        """Check if this is a soft (warning-only) dependency."""
        return self.strength == "soft"

    @property
    def is_count_based(self) -> bool:
        """Check if this requires multiple upstream completions."""
        return self.required_occurrence_count > 1

    def __repr__(self) -> str:
        strength_icon = "🛡️" if self.is_hard else "⚠️"
        return (
            f"<DependencyRule {strength_icon} "
            f"upstream={self.upstream_task_id[:8]}→downstream={self.downstream_task_id[:8]}>"
        )


class DependencyResolution(Base, UUIDMixin):
    """Tracks which upstream completion(s) satisfied a downstream completion."""

    __tablename__ = "dependency_resolutions"

    dependency_rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("dependency_rules.id", ondelete="CASCADE"),
        nullable=False,
    )

    downstream_completion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("task_completions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Which upstream completion satisfied this? NULL if overridden without completion.
    upstream_completion_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("task_completions.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # For count-based deps: which of N required completions is this? (1-indexed)
    # e.g., occurrence_index=3 means "this is the 3rd of 4 required waters"
    occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # How was this resolution created?
    resolution_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="manual"
    )

    # Override reason (only populated when resolution_source = 'override')
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    rule: Mapped["DependencyRule"] = relationship(back_populates="resolutions")
    downstream_completion: Mapped["TaskCompletion"] = relationship(
        foreign_keys=[downstream_completion_id],
        back_populates="dependency_resolutions_as_downstream",
    )
    upstream_completion: Mapped[Optional["TaskCompletion"]] = relationship(
        foreign_keys=[upstream_completion_id],
        back_populates="dependency_resolutions_as_upstream",
    )

    __table_args__ = (
        CheckConstraint(
            "resolution_source IN ('manual', 'chain', 'override', 'system')",
            name="check_resolution_source_values",
        ),
        CheckConstraint(
            "(resolution_source != 'override') OR (upstream_completion_id IS NULL)",
            name="check_override_has_no_upstream",
        ),
        Index("idx_dep_resolutions_rule", "dependency_rule_id"),
        Index("idx_dep_resolutions_downstream", "downstream_completion_id"),
        Index("idx_dep_resolutions_upstream", "upstream_completion_id"),
        # NOTE: Partial unique index for no-double-consumption created in migration
        # (SQLAlchemy doesn't support partial indexes in table_args)
    )

    @property
    def is_override(self) -> bool:
        """Check if this resolution was created via override."""
        return self.resolution_source == "override"

    @property
    def is_chain(self) -> bool:
        """Check if this resolution was created via chain completion."""
        return self.resolution_source == "chain"

    def __repr__(self) -> str:
        source_icon = {"manual": "👤", "chain": "⛓️", "override": "⚡", "system": "🤖"}
        icon = source_icon.get(self.resolution_source, "?")
        return f"<DependencyResolution {icon} rule={self.dependency_rule_id[:8]}>"


class DependencyStateCache(Base):
    """Caches dependency readiness state for responsive UI badges."""

    __tablename__ = "dependency_state_cache"

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Specific occurrence time (supports intra-day recurring tasks)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )

    # Readiness state
    readiness_state: Mapped[str] = mapped_column(String(20), nullable=False)

    unmet_hard_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmet_soft_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # For count-based: progress percentage (75 = 3 of 4)
    total_progress_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationship
    task: Mapped["Task"] = relationship(back_populates="dependency_state_cache")

    __table_args__ = (
        CheckConstraint(
            "readiness_state IN ('ready', 'blocked', 'partial', 'advisory')",
            name="check_readiness_state_values",
        ),
        Index("idx_dep_state_cache_time", "scheduled_for", "readiness_state"),
    )

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are met."""
        return self.readiness_state == "ready"

    @property
    def is_blocked(self) -> bool:
        """Check if blocked by hard dependency."""
        return self.readiness_state == "blocked"

    @property
    def is_partial(self) -> bool:
        """Check if some deps met, some not."""
        return self.readiness_state == "partial"

    @property
    def is_advisory(self) -> bool:
        """Check if only soft deps unmet (still completable)."""
        return self.readiness_state == "advisory"

    def __repr__(self) -> str:
        state_icon = {
            "ready": "●",
            "blocked": "○",
            "partial": "◐",
            "advisory": "◌",
        }
        icon = state_icon.get(self.readiness_state, "?")
        return f"<DependencyStateCache {icon} task={self.task_id[:8]}>"
