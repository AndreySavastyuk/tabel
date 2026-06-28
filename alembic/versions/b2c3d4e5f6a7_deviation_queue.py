"""deviation work-queue

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28 13:00:00.000000

Очередь отклонений с жизненным циклом: deviation_items (стабильный ключ
employee_id|work_date|dev_code, статусы, ответственный, is_present) и
deviation_comments (аудит смены статуса).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'deviation_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dedup_key', sa.String(length=80), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('work_date', sa.String(length=10), nullable=False),
        sa.Column('dev_code', sa.String(length=40), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('is_present', sa.Boolean(), nullable=False),
        sa.Column('assignee_id', sa.Integer(), nullable=True),
        sa.Column('dept_name', sa.String(length=255), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['pipeline_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dedup_key', name='uq_deviation_dedup'),
    )
    with op.batch_alter_table('deviation_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deviation_items_assignee_id'), ['assignee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deviation_items_dedup_key'), ['dedup_key'], unique=True)
        batch_op.create_index(batch_op.f('ix_deviation_items_department_id'), ['department_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deviation_items_dev_code'), ['dev_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_deviation_items_employee_id'), ['employee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deviation_items_run_id'), ['run_id'], unique=False)
        batch_op.create_index('ix_deviation_items_status_dept', ['status', 'department_id'], unique=False)

    op.create_table(
        'deviation_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('deviation_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('old_status', sa.String(length=12), nullable=True),
        sa.Column('new_status', sa.String(length=12), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['deviation_id'], ['deviation_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('deviation_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deviation_comments_deviation_id'), ['deviation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('deviation_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deviation_comments_deviation_id'))
    op.drop_table('deviation_comments')
    with op.batch_alter_table('deviation_items', schema=None) as batch_op:
        batch_op.drop_index('ix_deviation_items_status_dept')
        batch_op.drop_index(batch_op.f('ix_deviation_items_run_id'))
        batch_op.drop_index(batch_op.f('ix_deviation_items_employee_id'))
        batch_op.drop_index(batch_op.f('ix_deviation_items_dev_code'))
        batch_op.drop_index(batch_op.f('ix_deviation_items_department_id'))
        batch_op.drop_index(batch_op.f('ix_deviation_items_dedup_key'))
        batch_op.drop_index(batch_op.f('ix_deviation_items_assignee_id'))
    op.drop_table('deviation_items')
