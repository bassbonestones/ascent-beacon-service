"""
Add is_stashed to priorities

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from db_helpers import is_postgresql

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

def upgrade():
    default_val = sa.false() if is_postgresql() else sa.text('0')
    op.add_column('priorities', sa.Column('is_stashed', sa.Boolean(), nullable=False, server_default=default_val))
    # Only drop default on PostgreSQL (SQLite doesn't support it)
    if is_postgresql():
        op.alter_column('priorities', 'is_stashed', server_default=None)

def downgrade():
    op.drop_column('priorities', 'is_stashed')
