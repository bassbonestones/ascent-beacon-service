"""value_discovery_prompts

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create value_prompts table
    op.create_table(
        "value_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_text", sa.String(), nullable=False),
        sa.Column("primary_lens", sa.String(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Create user_value_selections table
    op.create_table(
        "user_value_selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("value_prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(), nullable=False, server_default="'important'"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custom_text", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create unique constraint
    op.create_unique_constraint(
        "uq_user_prompt",
        "user_value_selections",
        ["user_id", "prompt_id"],
    )

    # Create indexes for common queries
    op.create_index(
        "ix_user_value_selections_user_bucket",
        "user_value_selections",
        ["user_id", "bucket"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_value_selections_user_bucket")
    op.drop_table("user_value_selections")
    op.drop_table("value_prompts")
