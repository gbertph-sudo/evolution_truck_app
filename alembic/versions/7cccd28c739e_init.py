"""init

Revision ID: 7cccd28c739e
Revises: xxxx
Create Date: 2026-01-25 22:59:22.571865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cccd28c739e'
down_revision: Union[str, Sequence[str], None] = 'xxxx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
