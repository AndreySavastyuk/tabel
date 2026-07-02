"""employee overtime_tracked flag

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-01 12:00:00.000000

Флаг «ведём учёт переработок» у сотрудника (у части персонала переработки
считаются поквартально). server_default бэкфиллит существующие строки.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('overtime_tracked', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('overtime_tracked')
