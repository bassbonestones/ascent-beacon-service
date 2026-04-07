"""Add anytime task support with sort_order

Revision ID: 0019
Revises: 0018

Anytime tasks are unscheduled tasks that:
- Have no date, no time, never become overdue
- Use scheduling_mode='anytime'
- Have a user-controlled sort_order for manual ordering
- Show in a separate "Anytime" tab in the UI
"""
from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    # Add sort_order column for manual task ordering (anytime tasks only)
    # NULL for non-anytime tasks, integer for anytime (lower = higher in list)
    op.add_column(
        'tasks',
        sa.Column('sort_order', sa.Integer(), nullable=True)
    )
    
    # Create index for efficient querying of anytime tasks sorted by user
    # (user_id, scheduling_mode) lets us quickly get all anytime tasks for a user
    op.create_index(
        'ix_tasks_user_scheduling_mode',
        'tasks',
        ['user_id', 'scheduling_mode']
    )
    
    # Create index for sorting anytime tasks by sort_order
    # (user_id, sort_order) for efficient ORDER BY when fetching anytime list
    op.create_index(
        'ix_tasks_user_sort_order',
        'tasks',
        ['user_id', 'sort_order']
    )


def downgrade():
    op.drop_index('ix_tasks_user_sort_order', table_name='tasks')
    op.drop_index('ix_tasks_user_scheduling_mode', table_name='tasks')
    op.drop_column('tasks', 'sort_order')
