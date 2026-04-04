"""
Create goals and goal_priority_links tables

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from db_helpers import uuid_column, is_postgresql


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create goals table
    bool_default = "true" if is_postgresql() else "1"
    op.create_table(
        "goals",
        sa.Column("id", uuid_column(), primary_key=True),
        sa.Column(
            "user_id",
            uuid_column(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_goal_id",
            uuid_column(),
            sa.ForeignKey("goals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="'not_started'"),
        # Progress cached for performance
        sa.Column("progress_cached", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_incomplete_breakdown", sa.Boolean(), nullable=False, server_default=bool_default),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for common queries
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.create_index("ix_goals_parent_goal_id", "goals", ["parent_goal_id"])
    op.create_index("ix_goals_status", "goals", ["status"])
    op.create_index("ix_goals_user_status", "goals", ["user_id", "status"])

    # Create goal_priority_links table (many-to-many)
    op.create_table(
        "goal_priority_links",
        sa.Column("id", uuid_column(), primary_key=True),
        sa.Column(
            "goal_id",
            uuid_column(),
            sa.ForeignKey("goals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "priority_id",
            uuid_column(),
            sa.ForeignKey("priorities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("goal_id", "priority_id", name="uq_goal_priority"),
    )

    # Create indexes for goal_priority_links
    op.create_index("ix_goal_priority_links_goal_id", "goal_priority_links", ["goal_id"])
    op.create_index("ix_goal_priority_links_priority_id", "goal_priority_links", ["priority_id"])


def downgrade() -> None:
    op.drop_index("ix_goal_priority_links_priority_id")
    op.drop_index("ix_goal_priority_links_goal_id")
    op.drop_table("goal_priority_links")
    op.drop_index("ix_goals_user_status")
    op.drop_index("ix_goals_status")
    op.drop_index("ix_goals_parent_goal_id")
    op.drop_index("ix_goals_user_id")
    op.drop_table("goals")
