"""Add priority scope, score, cadence, constraints and rename fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to priority_revisions
    op.add_column('priority_revisions', sa.Column('why_matters', sa.String(), nullable=True))
    op.add_column('priority_revisions', sa.Column('score', sa.Integer(), nullable=True))
    op.add_column('priority_revisions', sa.Column('scope', sa.String(), nullable=True))
    op.add_column('priority_revisions', sa.Column('cadence', sa.String(), nullable=True))
    op.add_column('priority_revisions', sa.Column('constraints', postgresql.JSONB(), nullable=True))
    
    # Set defaults for existing records
    op.execute("UPDATE priority_revisions SET why_matters = body WHERE why_matters IS NULL")
    op.execute("UPDATE priority_revisions SET score = 3 WHERE score IS NULL")
    op.execute("UPDATE priority_revisions SET scope = 'ongoing' WHERE scope IS NULL")
    
    # Make new columns NOT NULL after setting defaults
    op.alter_column('priority_revisions', 'why_matters', existing_type=sa.String(), nullable=False)
    op.alter_column('priority_revisions', 'score', existing_type=sa.Integer(), nullable=False)
    op.alter_column('priority_revisions', 'scope', existing_type=sa.String(), nullable=False)
    
    # Drop old columns
    op.drop_column('priority_revisions', 'body')
    op.drop_column('priority_revisions', 'strength')


def downgrade():
    # Restore old columns
    op.add_column('priority_revisions', sa.Column('body', sa.String(), nullable=True))
    op.add_column('priority_revisions', sa.Column('strength', sa.Numeric(), nullable=True))
    
    # Copy data back
    op.execute("UPDATE priority_revisions SET body = why_matters WHERE body IS NULL")
    op.execute("UPDATE priority_revisions SET strength = 1.0 WHERE strength IS NULL")
    
    # Remove new columns
    op.drop_column('priority_revisions', 'why_matters')
    op.drop_column('priority_revisions', 'score')
    op.drop_column('priority_revisions', 'scope')
    op.drop_column('priority_revisions', 'cadence')
    op.drop_column('priority_revisions', 'constraints')
