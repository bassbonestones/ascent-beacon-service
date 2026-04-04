"""
Add source_prompt_id to value_revisions for tracking which discovery prompts were used

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from db_helpers import is_postgresql, uuid_column


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if is_postgresql():
        # PostgreSQL: Can add column with FK directly
        op.add_column(
            'value_revisions',
            sa.Column(
                'source_prompt_id',
                postgresql.UUID(as_uuid=False),
                nullable=True,
            )
        )
        op.create_foreign_key(
            'fk_value_revisions_source_prompt',
            'value_revisions',
            'value_prompts',
            ['source_prompt_id'],
            ['id'],
            ondelete='SET NULL'
        )
        op.create_index(
            'idx_value_revisions_source_prompt_id',
            'value_revisions',
            ['source_prompt_id']
        )
    else:
        # SQLite: Use batch mode for ALTER operations
        with op.batch_alter_table('value_revisions', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('source_prompt_id', sa.String(36), nullable=True)
            )
            # SQLite doesn't enforce FK constraints by default
            # Index only if supported
        op.create_index(
            'idx_value_revisions_source_prompt_id',
            'value_revisions',
            ['source_prompt_id']
        )


def downgrade() -> None:
    op.drop_index('idx_value_revisions_source_prompt_id', table_name='value_revisions')
    if is_postgresql():
        op.drop_constraint('fk_value_revisions_source_prompt', 'value_revisions', type_='foreignkey')
        op.drop_column('value_revisions', 'source_prompt_id')
    else:
        with op.batch_alter_table('value_revisions', schema=None) as batch_op:
            batch_op.drop_column('source_prompt_id')
