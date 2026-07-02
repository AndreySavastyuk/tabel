"""employee dismissed_at (дата увольнения)

Revision ID: 6d1e49a3ea0c
Revises: f7a8b9c0d1e2
Create Date: 2026-07-02 12:00:00.000000

Дата увольнения (последний рабочий день) у сотрудника. NULL — работает.
Уволенные скрываются из списков по умолчанию; с даты увольнения отклонения дня
не заводятся (сдача пропуска ломает отметки последнего дня). Revision id
СЛУЧАЙНЫЙ — не продолжать hex-шаблон соседних ревизий (см. коллизию
f7a8b9c0d1e2 с потерянной ранней реализацией arrives_by_car).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d1e49a3ea0c'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dismissed_at', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('dismissed_at')
