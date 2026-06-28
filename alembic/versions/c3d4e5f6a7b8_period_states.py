"""period close states

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-28 14:00:00.000000

Состояние закрытия месяца (period_states): факт закрытия/переоткрытия и выбор
активного (финального) прогона периода.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'period_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('active_run_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('reopened_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['active_run_id'], ['pipeline_runs.id'], ),
        sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('period_states', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_period_states_active_run_id'), ['active_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_period_states_period'), ['period'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('period_states', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_period_states_period'))
        batch_op.drop_index(batch_op.f('ix_period_states_active_run_id'))
    op.drop_table('period_states')
