"""Legacy goal status `abandoned` -> archived; status column no longer uses abandoned.

Revision ID: 0026_derived_goal_status_abandoned
Revises: 0025_phase_4j_record_state
"""

from alembic import op

revision = "0026_derived_goal_status_abandoned"
down_revision = "0025_phase_4j_record_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE goals
        SET record_state = 'archived',
            archived_at = COALESCE(archived_at, NOW()),
            status = 'not_started',
            completed_at = NULL
        WHERE status = 'abandoned'
        """
    )


def downgrade() -> None:
    """Abandoned status is no longer a supported value; downgrade is a no-op."""
    pass
