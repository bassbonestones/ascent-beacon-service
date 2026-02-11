"""value_similarity_fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "value_revisions",
        sa.Column(
            "similar_value_revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("value_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "value_revisions",
        sa.Column("similarity_score", sa.Numeric(), nullable=True),
    )
    op.add_column(
        "value_revisions",
        sa.Column(
            "similarity_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("value_revisions", "similarity_acknowledged")
    op.drop_column("value_revisions", "similarity_score")
    op.drop_column("value_revisions", "similar_value_revision_id")
