"""Add occurrence ordering tables for task reordering in Today/Upcoming views

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa
from db_helpers import uuid_column, is_postgresql, now_default

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    # Permanent relative ordering preferences
    op.create_table(
        'occurrence_preferences',
        sa.Column('id', uuid_column(),
                  server_default=sa.text('gen_random_uuid()') if is_postgresql() else None,
                  nullable=False),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('task_id', uuid_column(), nullable=False),
        sa.Column('occurrence_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sequence_number', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'task_id', 'occurrence_index', 
                           name='uq_occurrence_pref_user_task_idx')
    )
    op.create_index('idx_occurrence_pref_user', 'occurrence_preferences', ['user_id'])
    op.create_index('idx_occurrence_pref_task', 'occurrence_preferences', ['task_id'])
    
    # One-time daily sort overrides
    op.create_table(
        'daily_sort_overrides',
        sa.Column('id', uuid_column(),
                  server_default=sa.text('gen_random_uuid()') if is_postgresql() else None,
                  nullable=False),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('task_id', uuid_column(), nullable=False),
        sa.Column('occurrence_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('override_date', sa.String(10), nullable=False),  # YYYY-MM-DD
        sa.Column('sort_position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'task_id', 'occurrence_index', 'override_date',
                           name='uq_daily_override_user_task_idx_date')
    )
    op.create_index('idx_daily_override_user', 'daily_sort_overrides', ['user_id'])
    op.create_index('idx_daily_override_user_date', 'daily_sort_overrides', 
                    ['user_id', 'override_date'])


def downgrade():
    op.drop_table('daily_sort_overrides')
    op.drop_table('occurrence_preferences')
