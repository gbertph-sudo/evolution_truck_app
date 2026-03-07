"""add company_id and work_order_number to work_orders

Revision ID: 017f85272b77
Revises: 159a44792711
Create Date: 2026-02-22 23:31:44.131387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017f85272b77'
down_revision: Union[str, Sequence[str], None] = '159a44792711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_work_orders_company_id_companies"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("work_orders", sa.Column("work_order_number", sa.String(length=30), nullable=True))
    op.add_column("work_orders", sa.Column("company_id", sa.Integer(), nullable=True))

    op.create_index(op.f("ix_work_orders_company_id"), "work_orders", ["company_id"], unique=False)
    op.create_index(op.f("ix_work_orders_work_order_number"), "work_orders", ["work_order_number"], unique=True)

    op.create_foreign_key(
        FK_NAME,
        "work_orders",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(FK_NAME, "work_orders", type_="foreignkey")

    op.drop_index(op.f("ix_work_orders_work_order_number"), table_name="work_orders")
    op.drop_index(op.f("ix_work_orders_company_id"), table_name="work_orders")

    op.drop_column("work_orders", "company_id")
    op.drop_column("work_orders", "work_order_number")