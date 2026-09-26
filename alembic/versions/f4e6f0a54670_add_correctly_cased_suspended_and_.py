"""add correctly cased SUSPENDED and BANNED to account_status enum

Revision ID: f4e6f0a54670
Revises: 08d8e3d82c38
Create Date: 2026-09-26 16:17:12.534794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4e6f0a54670'
down_revision: Union[str, Sequence[str], None] = '08d8e3d82c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'SUSPENDED'")
    op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'BANNED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
