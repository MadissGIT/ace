"""playoff match participants on delete set null

Revision ID: 072952f5fc69
Revises: e41b9bbf4b9d
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '072952f5fc69'
down_revision: Union[str, None] = 'e41b9bbf4b9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Пересоздаём FK-констрейнты с ON DELETE SET NULL,
    # чтобы при удалении участника матчи плейофф не блокировали операцию.
    for col in ('participant1_id', 'participant2_id', 'winner_id'):
        op.drop_constraint(
            f'playoff_matches_{col}_fkey',
            'playoff_matches',
            type_='foreignkey',
        )
        op.create_foreign_key(
            f'playoff_matches_{col}_fkey',
            'playoff_matches',
            'tournament_participants',
            [col],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    for col in ('participant1_id', 'participant2_id', 'winner_id'):
        op.drop_constraint(
            f'playoff_matches_{col}_fkey',
            'playoff_matches',
            type_='foreignkey',
        )
        op.create_foreign_key(
            f'playoff_matches_{col}_fkey',
            'playoff_matches',
            'tournament_participants',
            [col],
            ['id'],
        )
