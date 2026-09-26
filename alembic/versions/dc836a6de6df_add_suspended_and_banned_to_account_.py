"""add suspended and banned to account_status enum

Revision ID: dc836a6de6df
Revises: e9dcaccb062c
Create Date: 2026-09-26 14:29:47.541685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc836a6de6df'
down_revision: Union[str, Sequence[str], None] = 'e9dcaccb062c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'suspended'")
    op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'banned'")


def downgrade() -> None:
    pass
