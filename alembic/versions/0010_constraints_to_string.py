"""Change constraints column from JSONB to VARCHAR

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-11 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from db_helpers import is_postgresql

# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL: Change column type from JSONB to String
    # SQLite: Column is already JSON type which can store strings, no action needed
    if is_postgresql():
        op.alter_column(
            'priority_revisions',
            'constraints',
            existing_type=postgresql.JSONB(),
            type_=sa.String(),
            existing_nullable=True
        )


def downgrade():
    # Convert back to JSONB (PostgreSQL only)
    if is_postgresql():
        op.alter_column(
            'priority_revisions',
            'constraints',
            existing_type=sa.String(),
            type_=postgresql.JSONB(),
            existing_nullable=True
        )
