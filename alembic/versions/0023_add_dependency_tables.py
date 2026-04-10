"""Add dependency rules, resolutions, and state cache tables (Phase 4i)

Implements occurrence-based task dependency system where dependencies are 
evaluated occurrence-to-occurrence, not task-to-task.

Tables:
- dependency_rules: Defines relationships between tasks
- dependency_resolutions: Tracks which upstream completions satisfied downstream
- dependency_state_cache: Caches readiness state for responsive UI

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa
from db_helpers import uuid_column, is_postgresql, now_default

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create dependency_rules table
    op.create_table(
        'dependency_rules',
        sa.Column('id', uuid_column(),
                  server_default=sa.text('gen_random_uuid()') if is_postgresql() else None,
                  nullable=False),
        sa.Column('user_id', uuid_column(), nullable=False),
        sa.Column('upstream_task_id', uuid_column(), nullable=False),
        sa.Column('downstream_task_id', uuid_column(), nullable=False),
        
        # Strength: 'hard' (blocks) or 'soft' (warning only)
        sa.Column('strength', sa.String(10), nullable=False, server_default='soft'),
        
        # Scope: 'all_occurrences' | 'next_occurrence' | 'within_window'
        sa.Column('scope', sa.String(20), nullable=False, server_default='next_occurrence'),
        
        # Count: how many upstream completions required
        sa.Column('required_occurrence_count', sa.Integer(), nullable=False, server_default='1'),
        
        # Window: for 'within_window' scope, validity duration in minutes
        sa.Column('validity_window_minutes', sa.Integer(), nullable=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['upstream_task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['downstream_task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        
        # One rule per upstream-downstream pair
        sa.UniqueConstraint('upstream_task_id', 'downstream_task_id',
                           name='uq_dependency_rule_pair'),
        
        # CHECK constraints
        sa.CheckConstraint('upstream_task_id != downstream_task_id',
                          name='check_no_self_dependency'),
        sa.CheckConstraint("strength IN ('hard', 'soft')",
                          name='check_strength_values'),
        sa.CheckConstraint("scope IN ('all_occurrences', 'next_occurrence', 'within_window')",
                          name='check_scope_values'),
        sa.CheckConstraint('required_occurrence_count >= 1',
                          name='check_min_count'),
    )
    
    # Indexes for dependency_rules
    op.create_index('idx_dependency_rules_user', 'dependency_rules', ['user_id'])
    op.create_index('idx_dependency_rules_upstream', 'dependency_rules', ['upstream_task_id'])
    op.create_index('idx_dependency_rules_downstream', 'dependency_rules', ['downstream_task_id'])
    
    # 2. Create dependency_resolutions table
    op.create_table(
        'dependency_resolutions',
        sa.Column('id', uuid_column(),
                  server_default=sa.text('gen_random_uuid()') if is_postgresql() else None,
                  nullable=False),
        sa.Column('dependency_rule_id', uuid_column(), nullable=False),
        sa.Column('downstream_completion_id', uuid_column(), nullable=False),
        
        # Which upstream completion satisfied this? NULL if overridden.
        sa.Column('upstream_completion_id', uuid_column(), nullable=True),
        
        sa.Column('resolved_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        
        # For count-based deps: which of N required completions (1-indexed)
        sa.Column('occurrence_index', sa.Integer(), nullable=False, server_default='1'),
        
        # Resolution source: manual | chain | override | system
        sa.Column('resolution_source', sa.String(10), nullable=False, server_default='manual'),
        
        # Override reason (only for resolution_source='override')
        sa.Column('override_reason', sa.Text(), nullable=True),
        
        sa.ForeignKeyConstraint(['dependency_rule_id'], ['dependency_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['downstream_completion_id'], ['task_completions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['upstream_completion_id'], ['task_completions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        
        # CHECK constraints
        sa.CheckConstraint("resolution_source IN ('manual', 'chain', 'override', 'system')",
                          name='check_resolution_source_values'),
        sa.CheckConstraint(
            "(resolution_source != 'override') OR (upstream_completion_id IS NULL)",
            name='check_override_has_no_upstream'),
    )
    
    # Indexes for dependency_resolutions
    op.create_index('idx_dep_resolutions_rule', 'dependency_resolutions', ['dependency_rule_id'])
    op.create_index('idx_dep_resolutions_downstream', 'dependency_resolutions', ['downstream_completion_id'])
    op.create_index('idx_dep_resolutions_upstream', 'dependency_resolutions', ['upstream_completion_id'])
    
    # Prevent double consumption: same upstream completion can't satisfy same rule twice
    # NOTE: Consumption is PER-RULE - same upstream CAN satisfy DIFFERENT rules
    if is_postgresql():
        op.execute("""
            CREATE UNIQUE INDEX idx_dep_resolutions_no_double_consumption
            ON dependency_resolutions(dependency_rule_id, upstream_completion_id)
            WHERE upstream_completion_id IS NOT NULL
        """)
    else:
        # SQLite partial index syntax
        op.execute("""
            CREATE UNIQUE INDEX idx_dep_resolutions_no_double_consumption
            ON dependency_resolutions(dependency_rule_id, upstream_completion_id)
            WHERE upstream_completion_id IS NOT NULL
        """)
    
    # 3. Create dependency_state_cache table
    op.create_table(
        'dependency_state_cache',
        sa.Column('task_id', uuid_column(), nullable=False),
        # Specific occurrence time (supports intra-day recurring tasks)
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
        
        # Readiness state: ready | blocked | partial | advisory
        sa.Column('readiness_state', sa.String(20), nullable=False),
        
        sa.Column('unmet_hard_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unmet_soft_count', sa.Integer(), nullable=False, server_default='0'),
        
        # For count-based: progress percentage (75 = 3 of 4)
        sa.Column('total_progress_pct', sa.Integer(), nullable=True),
        
        sa.Column('cached_at', sa.DateTime(timezone=True),
                  server_default=now_default(), nullable=False),
        
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('task_id', 'scheduled_for'),
        
        # CHECK constraint
        sa.CheckConstraint("readiness_state IN ('ready', 'blocked', 'partial', 'advisory')",
                          name='check_readiness_state_values'),
    )
    
    # Indexes for dependency_state_cache
    op.create_index('idx_dep_state_cache_time', 'dependency_state_cache',
                    ['scheduled_for', 'readiness_state'])


def downgrade():
    op.drop_table('dependency_state_cache')
    op.drop_index('idx_dep_resolutions_no_double_consumption', table_name='dependency_resolutions')
    op.drop_table('dependency_resolutions')
    op.drop_table('dependency_rules')
