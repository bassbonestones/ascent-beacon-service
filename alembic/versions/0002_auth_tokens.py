"""auth_tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-09 12:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Email login tokens table
    op.create_table(
        'email_login_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('request_ip', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
    )
    op.create_index('idx_email_login_tokens_email', 'email_login_tokens', ['email'])
    op.create_index('idx_email_login_tokens_expires_at', 'email_login_tokens', ['expires_at'])
    
    # Refresh tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('device_name', sa.String(), nullable=True),
        sa.Column('last_ip', postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('idx_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'])


def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_table('email_login_tokens')
