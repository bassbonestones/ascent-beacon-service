"""Add priority scope, score, cadence, constraints and rename fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from db_helpers import jsonb_column, is_postgresql

# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to priority_revisions
    # For SQLite, add columns as NOT NULL with defaults directly since it's a fresh db
    if is_postgresql():
        op.add_column('priority_revisions', sa.Column('why_matters', sa.String(), nullable=True))
        op.add_column('priority_revisions', sa.Column('score', sa.Integer(), nullable=True))
        op.add_column('priority_revisions', sa.Column('scope', sa.String(), nullable=True))
        op.add_column('priority_revisions', sa.Column('cadence', sa.String(), nullable=True))
        op.add_column('priority_revisions', sa.Column('constraints', jsonb_column(), nullable=True))
        
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
    else:
        # SQLite: Use batch mode for complex table alterations
        with op.batch_alter_table('priority_revisions') as batch_op:
            batch_op.add_column(sa.Column('why_matters', sa.String(), nullable=False, server_default=''))
            batch_op.add_column(sa.Column('score', sa.Integer(), nullable=False, server_default='3'))
            batch_op.add_column(sa.Column('scope', sa.String(), nullable=False, server_default='ongoing'))
            batch_op.add_column(sa.Column('cadence', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('constraints', sa.JSON(), nullable=True))
            batch_op.drop_column('body')
            batch_op.drop_column('strength')


def downgrade():
    if is_postgresql():
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
    else:
        with op.batch_alter_table('priority_revisions') as batch_op:
            batch_op.add_column(sa.Column('body', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('strength', sa.Numeric(), nullable=True))
            batch_op.drop_column('why_matters')
            batch_op.drop_column('score')
            batch_op.drop_column('scope')
            batch_op.drop_column('cadence')
            batch_op.drop_column('constraints')
    op.drop_column('priority_revisions', 'constraints')
