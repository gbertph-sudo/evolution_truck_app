"""add_invoices

Revision ID: 764425c241b0
Revises: 18ef985d9bde
Create Date: 2026-01-26 00:55:13.321251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '764425c241b0'
down_revision: Union[str, Sequence[str], None] = '18ef985d9bde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
