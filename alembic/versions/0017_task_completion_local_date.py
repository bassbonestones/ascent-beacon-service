"""Add local_date column to task_completions for timezone-correct date tracking

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    # Add local_date column for storing the client's local date (YYYY-MM-DD)
    # This is used as the key for completions_by_date and skips_by_date
    # to ensure timezone-correct date matching
    op.add_column(
        'task_completions',
        sa.Column('local_date', sa.String(10), nullable=True)
    )


def downgrade():
    op.drop_column('task_completions', 'local_date')
