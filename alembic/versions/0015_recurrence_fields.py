"""
Add recurrence fields to tasks and create task_completions table.

Phase 4b: Recurrence Engine

Changes:
- Add scheduling_mode to tasks (floating/fixed for timezone handling)
- Add skip_reason to tasks (optional reason when skipping)
- Create task_completions table for recurring task history

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from db_helpers import uuid_column, is_postgresql, now_default


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to tasks table
    op.add_column(
        'tasks',
        sa.Column(
            'scheduling_mode',
            sa.String(),
            nullable=True,
            comment='floating = time-of-day (adjusts with timezone), fixed = timezone-locked'
        )
    )
    op.add_column(
        'tasks',
        sa.Column(
            'skip_reason',
            sa.String(),
            nullable=True,
            comment='Optional reason when task is skipped'
        )
    )

    # Create task_completions table for recurring task history
    op.create_table(
        'task_completions',
        sa.Column(
            'id',
            uuid_column(),
            server_default=sa.text('gen_random_uuid()') if is_postgresql() else None,
            nullable=False
        ),
        sa.Column('task_id', uuid_column(), nullable=False),

        # Status: completed | skipped
        sa.Column('status', sa.String(), nullable=False, server_default='completed'),

        # Optional reason when skipped
        sa.Column('skip_reason', sa.String(), nullable=True),

        # When the completion was recorded
        sa.Column('completed_at', sa.DateTime(timezone=True), server_default=now_default(), nullable=False),

        # When this occurrence was scheduled for (for tracking missed occurrences)
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=now_default(), nullable=False),

        # Constraints
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for task_completions
    op.create_index('idx_task_completions_task_id', 'task_completions', ['task_id'])
    op.create_index('idx_task_completions_completed_at', 'task_completions', ['completed_at'])
    op.create_index('idx_task_completions_scheduled_for', 'task_completions', ['scheduled_for'])
    op.create_index('idx_task_completions_task_status', 'task_completions', ['task_id', 'status'])


def downgrade() -> None:
    # Drop task_completions table
    op.drop_index('idx_task_completions_task_status', 'task_completions')
    op.drop_index('idx_task_completions_scheduled_for', 'task_completions')
    op.drop_index('idx_task_completions_completed_at', 'task_completions')
    op.drop_index('idx_task_completions_task_id', 'task_completions')
    op.drop_table('task_completions')

    # Remove columns from tasks table
    op.drop_column('tasks', 'skip_reason')
    op.drop_column('tasks', 'scheduling_mode')
