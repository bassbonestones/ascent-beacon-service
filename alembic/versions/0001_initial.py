"""initial

Revision ID: 0001
Revises: 
Create Date: 2026-02-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from db_helpers import is_postgresql, uuid_column, now_default

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL-specific extensions
    if is_postgresql():
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('primary_email', sa.String(), nullable=True),
    )
    op.create_index('idx_users_created_at', 'users', ['created_at'])
    
    # User identities table
    op.create_table(
        'user_identities',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('provider_subject', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider', 'provider_subject', name='uq_provider_subject'),
    )
    op.create_index('idx_user_identities_user_id', 'user_identities', ['user_id'])
    op.create_index('idx_user_identities_email', 'user_identities', ['email'])
    
    # Values table
    op.create_table(
        'values',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('active_revision_id', uuid_column(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_values_user_id', 'values', ['user_id'])
    
    # Value revisions table
    op.create_table(
        'value_revisions',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('value_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('statement', sa.String(), nullable=False),
        sa.Column('weight_raw', sa.Numeric(), nullable=False),
        sa.Column('weight_normalized', sa.Numeric(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('origin', sa.String(), nullable=False, server_default='declared'),
        sa.ForeignKeyConstraint(['value_id'], ['values.id'], ondelete='CASCADE'),
        sa.CheckConstraint("origin IN ('declared', 'explored')", name='ck_value_revision_origin'),
    )
    op.create_index('idx_value_revisions_value_id', 'value_revisions', ['value_id'])
    op.create_index('idx_value_revisions_is_active', 'value_revisions', ['is_active'])
    
    # Priorities table
    op.create_table(
        'priorities',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('active_revision_id', uuid_column(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_priorities_user_id', 'priorities', ['user_id'])
    
    # Priority revisions table
    op.create_table(
        'priority_revisions',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('priority_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=True),
        sa.Column('strength', sa.Numeric(), nullable=False, server_default='1.0'),
        sa.Column('is_anchored', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('notes', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['priority_id'], ['priorities.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_priority_revisions_priority_id', 'priority_revisions', ['priority_id'])
    op.create_index('idx_priority_revisions_is_active', 'priority_revisions', ['is_active'])
    op.create_index('idx_priority_revisions_is_anchored', 'priority_revisions', ['is_anchored'])
    
    # Priority-Value links table
    op.create_table(
        'priority_value_links',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('priority_revision_id', uuid_column(), nullable=False),
        sa.Column('value_revision_id', uuid_column(), nullable=False),
        sa.Column('link_weight', sa.Numeric(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.ForeignKeyConstraint(['priority_revision_id'], ['priority_revisions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['value_revision_id'], ['value_revisions.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('priority_revision_id', 'value_revision_id', name='uq_priority_value_link'),
    )
    op.create_index('idx_pvl_priority_rev', 'priority_value_links', ['priority_revision_id'])
    op.create_index('idx_pvl_value_rev', 'priority_value_links', ['value_revision_id'])


def downgrade() -> None:
    op.drop_table('priority_value_links')
    op.drop_table('priority_revisions')
    op.drop_table('priorities')
    op.drop_table('value_revisions')
    op.drop_table('values')
    op.drop_table('user_identities')
    op.drop_table('users')
    if is_postgresql():
        op.execute('DROP EXTENSION IF EXISTS "vector"')
        op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
