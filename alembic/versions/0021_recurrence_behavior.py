"""Add recurrence_behavior field to tasks table (Phase 4g)

Habitual vs Essential behavior for recurring tasks:
- 'habitual': Auto-skip missed occurrences on app open
- 'essential': Stays overdue until manually actioned

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    # Add recurrence_behavior column
    # Valid: 'habitual' | 'essential' | NULL
    # NULL for non-recurring tasks
    # Required for recurring tasks (enforced at API level)
    op.add_column(
        'tasks',
        sa.Column('recurrence_behavior', sa.String(), nullable=True)
    )
    
    # Create index for filtering by behavior
    op.create_index(
        'ix_tasks_recurrence_behavior',
        'tasks',
        ['recurrence_behavior']
    )


def downgrade():
    op.drop_index('ix_tasks_recurrence_behavior', table_name='tasks')
    op.drop_column('tasks', 'recurrence_behavior')
