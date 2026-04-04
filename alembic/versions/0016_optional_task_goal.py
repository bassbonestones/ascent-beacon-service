"""Make task goal_id optional

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-04

Tasks can exist without being linked to a goal.
Unaligned tasks will display differently in the UI.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make goal_id nullable and change ondelete to SET NULL."""
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # For PostgreSQL in production, this would be simpler
    
    # Create new table with nullable goal_id
    op.create_table(
        "tasks_new",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("goal_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.String(), nullable=False, default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduling_mode", sa.String(), nullable=True),
        sa.Column("recurrence_rule", sa.String(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, default=False),
        sa.Column("notify_before_minutes", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
    )
    
    # Copy data from old table
    op.execute("""
        INSERT INTO tasks_new 
        SELECT id, user_id, goal_id, title, description, duration_minutes, status,
               scheduled_at, scheduling_mode, recurrence_rule, is_recurring,
               notify_before_minutes, completed_at, skip_reason, created_at, updated_at
        FROM tasks
    """)
    
    # Drop old table and rename new one
    op.drop_table("tasks")
    op.rename_table("tasks_new", "tasks")
    
    # Recreate indexes
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_scheduled_at", "tasks", ["scheduled_at"])


def downgrade() -> None:
    """Make goal_id required again (will fail if any tasks have null goal_id)."""
    # Create new table with required goal_id
    op.create_table(
        "tasks_old",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("goal_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.String(), nullable=False, default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduling_mode", sa.String(), nullable=True),
        sa.Column("recurrence_rule", sa.String(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, default=False),
        sa.Column("notify_before_minutes", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
    )
    
    # Copy data (will fail if any tasks have null goal_id)
    op.execute("""
        INSERT INTO tasks_old 
        SELECT id, user_id, goal_id, title, description, duration_minutes, status,
               scheduled_at, scheduling_mode, recurrence_rule, is_recurring,
               notify_before_minutes, completed_at, skip_reason, created_at, updated_at
        FROM tasks
        WHERE goal_id IS NOT NULL
    """)
    
    # Drop new table and rename old one
    op.drop_table("tasks")
    op.rename_table("tasks_old", "tasks")
    
    # Recreate indexes
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_scheduled_at", "tasks", ["scheduled_at"])
