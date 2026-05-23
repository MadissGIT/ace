"""added vk id to users

Revision ID: 3d8b8f41f2a9
Revises: 072952f5fc69
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d8b8f41f2a9'
down_revision: Union[str, None] = '072952f5fc69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('vk_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_users_vk_id', 'users', ['vk_id'])


def downgrade() -> None:
    op.drop_constraint('uq_users_vk_id', 'users', type_='unique')
    op.drop_column('users', 'vk_id')
