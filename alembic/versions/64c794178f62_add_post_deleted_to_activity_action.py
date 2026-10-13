"""add POST_DELETED to activity_action

Revision ID: 64c794178f62
Revises: 96783d7e2aad
Create Date: 2026-10-11 15:13:59.602807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64c794178f62'
down_revision: Union[str, Sequence[str], None] = '96783d7e2aad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'POST_DELETED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
