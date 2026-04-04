"""Add unique constraint on primary_email

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-10 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from db_helpers import is_postgresql


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate users, keeping the oldest one for each email
    # SQLite compatible DELETE syntax
    if is_postgresql():
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
    else:
        # SQLite-compatible duplicate removal
        op.execute("""
        DELETE FROM users 
        WHERE ROWID NOT IN (
            SELECT MIN(ROWID) FROM users 
            GROUP BY primary_email
        ) AND primary_email IS NOT NULL
        """)
    
    # Add unique constraint - use batch mode for SQLite
    if is_postgresql():
        op.create_unique_constraint('uq_user_primary_email', 'users', ['primary_email'])
    else:
        with op.batch_alter_table('users') as batch_op:
            batch_op.create_unique_constraint('uq_user_primary_email', ['primary_email'])


def downgrade():
    if is_postgresql():
        op.drop_constraint('uq_user_primary_email', 'users', type_='unique')
    else:
        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_constraint('uq_user_primary_email', type_='unique')
