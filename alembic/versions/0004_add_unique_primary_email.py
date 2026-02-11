"""Add unique constraint on primary_email

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-10 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate users, keeping the oldest one for each email
    op.execute("""
    DELETE FROM users 
    WHERE id IN (
        SELECT id FROM users u1
        WHERE EXISTS (
            SELECT 1 FROM users u2 
            WHERE u1.primary_email = u2.primary_email 
            AND u1.primary_email IS NOT NULL
            AND u1.created_at > u2.created_at
        )
    )
    """)
    
    # Add unique constraint on primary_email (nullable, so multiple NULLs are allowed)
    op.execute("""
    ALTER TABLE users 
    ADD CONSTRAINT uq_user_primary_email UNIQUE (primary_email)
    """)


def downgrade():
    op.execute("""
    ALTER TABLE users 
    DROP CONSTRAINT uq_user_primary_email
    """)
