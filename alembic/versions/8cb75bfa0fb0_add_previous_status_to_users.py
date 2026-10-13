"""add previous_status to users

Revision ID: 8cb75bfa0fb0
Revises: f4e6f0a54670
Create Date: 2026-10-04 09:36:23.811796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8cb75bfa0fb0'
down_revision: Union[str, Sequence[str], None] = 'f4e6f0a54670'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "previous_status",
            postgresql.ENUM(name="account_status", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "previous_status")