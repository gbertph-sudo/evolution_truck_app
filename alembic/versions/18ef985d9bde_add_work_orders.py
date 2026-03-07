"""add_work_orders

Revision ID: 18ef985d9bde
Revises: 7cccd28c739e
Create Date: 2026-01-26 00:00:18.241340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18ef985d9bde'
down_revision: Union[str, Sequence[str], None] = '7cccd28c739e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
