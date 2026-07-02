"""employee arrives_by_car flag

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-02 18:00:00.000000

Флаг «заезжает на машине» у сотрудника: такой человек попадает на территорию
через автопроезд и не отмечается на проходной ЛЭЗ. Флаг гасит отклонение
«Только внутренняя система (нет ЛЭЗ)», даже если в другие дни он проходит ЛЭЗ
(перебивает dual_tracked). server_default бэкфиллит существующие строки в False.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('arrives_by_car', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('arrives_by_car')
