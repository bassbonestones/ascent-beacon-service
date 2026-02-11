"""Add is_email_verified field to users table

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-10 05:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('users', 'is_email_verified')
