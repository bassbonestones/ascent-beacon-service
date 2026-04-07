"""Add scheduled_date column to tasks for date-only scheduling

Revision ID: 0018
Revises: 0017

Separates date vs datetime scheduling:
- scheduled_date (string YYYY-MM-DD): For date-only tasks (no specific time)
- scheduled_at (datetime): For timed tasks (specific time)

When scheduled_date is set and scheduled_at is NULL, the task is "date-only".
When scheduled_at is set, it contains the full datetime.
"""
from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    # Add scheduled_date column for storing date without time (YYYY-MM-DD format)
    # This is separate from scheduled_at which stores datetime with time
    op.add_column(
        'tasks',
        sa.Column('scheduled_date', sa.String(), nullable=True)
    )
    
    # Create index for efficient date-based queries
    op.create_index('idx_tasks_scheduled_date', 'tasks', ['scheduled_date'])


def downgrade():
    op.drop_index('idx_tasks_scheduled_date', table_name='tasks')
    op.drop_column('tasks', 'scheduled_date')
