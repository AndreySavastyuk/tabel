"""deviation time decision (away-time deduction)

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-01 10:00:00.000000

Решение по времени вне территории на отклонении REENTRY_GAP: away_minutes
(суммарно отлучек за день), deduct_minutes (сколько вычесть из рабочего дня),
time_decision (pending/counted/deducted). server_default бэкфиллит старые строки
(как в run_period_finalization). ALTER через batch_alter_table (SQLite).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('deviation_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('away_minutes', sa.Integer(), nullable=False,
                                      server_default='0'))
        batch_op.add_column(sa.Column('deduct_minutes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('time_decision', sa.String(length=12),
                                      nullable=False, server_default='pending'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('deviation_items', schema=None) as batch_op:
        batch_op.drop_column('time_decision')
        batch_op.drop_column('deduct_minutes')
        batch_op.drop_column('away_minutes')
