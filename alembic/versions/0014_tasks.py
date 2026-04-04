"""
Create tasks table for task management.

Phase 4a: Core tasks - CRUD, one-time tasks, lightning tasks.
Includes placeholder columns for recurrence (Phase 4b).

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from db_helpers import uuid_column, is_postgresql, now_default


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', uuid_column(), server_default=sa.text('gen_random_uuid()') if is_postgresql() else None, nullable=False),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('goal_id', uuid_column(), nullable=False),
        
        # Core fields
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        
        # Duration: 0 = lightning task (<1 min)
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='0'),
        
        # Status: pending | completed | skipped
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        
        # Scheduling (when user plans to do it)
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        
        # Recurrence (Phase 4b) - RRULE string
        sa.Column('recurrence_rule', sa.String(), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default='false'),
        
        # Notifications (Phase 4f) - NULL = no notification
        sa.Column('notify_before_minutes', sa.Integer(), nullable=True),
        
        # Completion tracking (for non-recurring tasks)
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        
        # Constraints
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_tasks_user_id', 'tasks', ['user_id'])
    op.create_index('idx_tasks_goal_id', 'tasks', ['goal_id'])
    op.create_index('idx_tasks_status', 'tasks', ['status'])
    op.create_index('idx_tasks_scheduled_at', 'tasks', ['scheduled_at'])
    op.create_index('idx_tasks_is_recurring', 'tasks', ['is_recurring'])
    op.create_index('idx_tasks_user_status', 'tasks', ['user_id', 'status'])


def downgrade() -> None:
    op.drop_index('idx_tasks_user_status', 'tasks')
    op.drop_index('idx_tasks_is_recurring', 'tasks')
    op.drop_index('idx_tasks_scheduled_at', 'tasks')
    op.drop_index('idx_tasks_status', 'tasks')
    op.drop_index('idx_tasks_goal_id', 'tasks')
    op.drop_index('idx_tasks_user_id', 'tasks')
    op.drop_table('tasks')
