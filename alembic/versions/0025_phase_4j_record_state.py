"""Phase 4j: record_state on goals and tasks, archive fields, unaligned acknowledgment.

Revision ID: 0025_phase_4j_record_state
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa

revision = "0025_phase_4j_record_state"
down_revision = "0024_dep_resolution_unique_per_downstream"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "goals",
        sa.Column(
            "record_state",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "goals",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "goals",
        sa.Column("archive_tracking_mode", sa.String(), nullable=True),
    )
    op.create_index("ix_goals_record_state", "goals", ["record_state"])

    op.add_column(
        "tasks",
        sa.Column(
            "record_state",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "unaligned_execution_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_tasks_record_state", "tasks", ["record_state"])


def downgrade() -> None:
    op.drop_index("ix_tasks_record_state", table_name="tasks")
    op.drop_column("tasks", "unaligned_execution_acknowledged_at")
    op.drop_column("tasks", "record_state")

    op.drop_index("ix_goals_record_state", table_name="goals")
    op.drop_column("goals", "archive_tracking_mode")
    op.drop_column("goals", "archived_at")
    op.drop_column("goals", "record_state")
