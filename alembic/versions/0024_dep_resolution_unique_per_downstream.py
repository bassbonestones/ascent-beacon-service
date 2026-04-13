"""Allow same upstream completion to resolve all_occurrences for multiple downstream completions.

Revision ID: 0024_dep_resolution_unique_per_downstream
Revises: 0023
"""

from alembic import op

revision = "0024_dep_resolution_unique_per_downstream"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "idx_dep_resolutions_no_double_consumption",
        table_name="dependency_resolutions",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX idx_dep_resolutions_no_double_consumption
        ON dependency_resolutions(
            dependency_rule_id,
            upstream_completion_id,
            downstream_completion_id
        )
        WHERE upstream_completion_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dep_resolutions_no_double_consumption",
        table_name="dependency_resolutions",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX idx_dep_resolutions_no_double_consumption
        ON dependency_resolutions(dependency_rule_id, upstream_completion_id)
        WHERE upstream_completion_id IS NOT NULL
        """
    )
