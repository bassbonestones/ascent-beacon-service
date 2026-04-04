"""assistant_voice_embeddings

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-09 12:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from db_helpers import is_postgresql, uuid_column, now_default, jsonb_column

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Embeddings table (PostgreSQL only - requires pgvector)
    if is_postgresql():
        from pgvector.sqlalchemy import Vector
        op.create_table(
            'embeddings',
            sa.Column('id', uuid_column(), primary_key=True),
            sa.Column('entity_type', sa.String(), nullable=False),
            sa.Column('entity_id', uuid_column(), nullable=False),
            sa.Column('model', sa.String(), nullable=False),
            sa.Column('dims', sa.Integer(), nullable=False),
            sa.Column('embedding', Vector(3072), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
            sa.CheckConstraint("entity_type IN ('value_revision', 'priority_revision')", name='ck_embedding_entity_type'),
            sa.UniqueConstraint('entity_type', 'entity_id', 'model', name='uq_embedding_entity_model'),
        )
        op.create_index('idx_embeddings_entity', 'embeddings', ['entity_type', 'entity_id'])
    else:
        # SQLite: Create embeddings table without vector column (for schema compatibility)
        op.create_table(
            'embeddings',
            sa.Column('id', uuid_column(), primary_key=True),
            sa.Column('entity_type', sa.String(), nullable=False),
            sa.Column('entity_id', uuid_column(), nullable=False),
            sa.Column('model', sa.String(), nullable=False),
            sa.Column('dims', sa.Integer(), nullable=False),
            sa.Column('embedding', sa.Text(), nullable=True),  # Store as JSON string in SQLite
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        )
        op.create_index('idx_embeddings_entity', 'embeddings', ['entity_type', 'entity_id'])
    
    # Assistant sessions table
    op.create_table(
        'assistant_sessions',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('context_mode', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1') if not is_postgresql() else sa.text('true')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_assistant_sessions_user_id', 'assistant_sessions', ['user_id'])
    
    # Assistant turns table
    op.create_table(
        'assistant_turns',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('session_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('input_modality', sa.String(), nullable=False, server_default='text'),
        sa.Column('stt_provider', sa.String(), nullable=True),
        sa.Column('stt_confidence', sa.Numeric(), nullable=True),
        sa.Column('llm_provider', sa.String(), nullable=True),
        sa.Column('llm_model', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['assistant_sessions.id'], ondelete='CASCADE'),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name='ck_assistant_turn_role'),
        sa.CheckConstraint("input_modality IN ('text', 'voice')", name='ck_assistant_turn_modality'),
    )
    op.create_index('idx_assistant_turns_session_id', 'assistant_turns', ['session_id'])
    op.create_index('idx_assistant_turns_created_at', 'assistant_turns', ['created_at'])
    
    # Assistant recommendations table
    op.create_table(
        'assistant_recommendations',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('session_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('status', sa.String(), nullable=False, server_default='proposed'),
        sa.Column('proposed_action', sa.String(), nullable=False),
        sa.Column('payload', jsonb_column(), nullable=False),
        sa.Column('rationale', sa.String(), nullable=True),
        sa.Column('llm_provider', sa.String(), nullable=False),
        sa.Column('llm_model', sa.String(), nullable=False),
        sa.Column('result_entity_type', sa.String(), nullable=True),
        sa.Column('result_entity_id', uuid_column(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['assistant_sessions.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'rejected', 'expired')",
            name='ck_assistant_recommendation_status'
        ),
        sa.CheckConstraint(
            "proposed_action IN ('create_value', 'create_priority', 'set_links', 'suggest_anchors', 'rewrite_text', 'alignment_reflection')",
            name='ck_assistant_recommendation_action'
        ),
    )
    op.create_index('idx_assistant_recs_session_id', 'assistant_recommendations', ['session_id'])
    op.create_index('idx_assistant_recs_status', 'assistant_recommendations', ['status'])
    
    # STT requests table
    op.create_table(
        'stt_requests',
        sa.Column('id', uuid_column(), primary_key=True),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=now_default()),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('audio_seconds', sa.Numeric(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('transcript', sa.String(), nullable=True),
        sa.Column('confidence', sa.Numeric(), nullable=True),
        sa.Column('error_code', sa.String(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('received', 'transcribed', 'failed')", name='ck_stt_request_status'),
    )
    op.create_index('idx_stt_requests_user_id', 'stt_requests', ['user_id'])
    op.create_index('idx_stt_requests_created_at', 'stt_requests', ['created_at'])


def downgrade() -> None:
    op.drop_table('stt_requests')
    op.drop_table('assistant_recommendations')
    op.drop_table('assistant_turns')
    op.drop_table('assistant_sessions')
    op.drop_table('embeddings')
