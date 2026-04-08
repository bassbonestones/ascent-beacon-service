"""Add source field to task_completions table (Phase 4h)

Tracks whether a completion record was created from real user interaction
or mocked via the Rhythm History Simulator for testing.

Values:
- 'REAL': Normal user interaction (default)
- 'MOCK': Created via Rhythm History Simulator

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    # Add source column with default 'REAL' for existing records
    op.add_column(
        'task_completions',
        sa.Column('source', sa.String(10), nullable=True, server_default='REAL')
    )


def downgrade():
    op.drop_column('task_completions', 'source')
