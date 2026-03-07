"""add_inventory

Revision ID: cea0d27056c7
Revises: 764425c241b0
Create Date: 2026-01-26 01:23:49.613793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cea0d27056c7'
down_revision: Union[str, Sequence[str], None] = '764425c241b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
