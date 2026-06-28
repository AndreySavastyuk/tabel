"""run period + finalization

Revision ID: a1b2c3d4e5f6
Revises: d4c8b9a637ce
Create Date: 2026-06-28 12:00:00.000000

Добавляет ось периода и финализацию прогона: period_label (YYYY-MM для месячных
прогонов), is_final (утверждённый прогон периода), finalized_at/finalized_by.
period_from/period_to уже существуют (phase2) — начинают заполняться кодом.
ALTER через batch_alter_table — для SQLite (alembic/env.py render_as_batch).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd4c8b9a637ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('period_label', sa.String(length=7), nullable=True))
        batch_op.add_column(sa.Column('is_final', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('finalized_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('finalized_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_pipeline_runs_finalized_by_users',
                                    'users', ['finalized_by'], ['id'])
        batch_op.create_index(batch_op.f('ix_pipeline_runs_period_label'),
                              ['period_label'], unique=False)
        batch_op.create_index(batch_op.f('ix_pipeline_runs_is_final'),
                              ['is_final'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pipeline_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pipeline_runs_is_final'))
        batch_op.drop_index(batch_op.f('ix_pipeline_runs_period_label'))
        batch_op.drop_constraint('fk_pipeline_runs_finalized_by_users', type_='foreignkey')
        batch_op.drop_column('finalized_by')
        batch_op.drop_column('finalized_at')
        batch_op.drop_column('is_final')
        batch_op.drop_column('period_label')
