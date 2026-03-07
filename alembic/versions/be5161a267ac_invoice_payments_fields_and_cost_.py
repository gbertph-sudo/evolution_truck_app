"""invoice payments fields and cost_snapshot

Revision ID: be5161a267ac
Revises: b5c66b3dc0ee
Create Date: 2026-03-02 00:44:58.568212
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "be5161a267ac"
down_revision: Union[str, Sequence[str], None] = "b5c66b3dc0ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------
    # invoices: payment fields
    # -------------------------
    op.add_column("invoices", sa.Column("payment_method", sa.String(length=20), nullable=True))

    op.add_column(
        "invoices",
        sa.Column("processing_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
    )

    op.add_column("invoices", sa.Column("paid_at", sa.DateTime(), nullable=True))

    # índice para filtrar rápido por payment_method
    op.create_index("ix_invoices_payment_method", "invoices", ["payment_method"], unique=False)

    # -------------------------
    # invoice_items: cost snapshot
    # -------------------------
    op.add_column(
        "invoice_items",
        sa.Column("cost_snapshot", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
    )

    # (Opcional pero recomendado) quitar server_default a futuro:
    # En Postgres, si quieres dejar el default permanente, déjalo.
    # Si quieres SOLO para migración (viejas filas) y luego quitarlo:
    # op.alter_column("invoices", "processing_fee", server_default=None)
    # op.alter_column("invoice_items", "cost_snapshot", server_default=None)


def downgrade() -> None:
    # revertimos en orden inverso
    op.drop_column("invoice_items", "cost_snapshot")

    op.drop_index("ix_invoices_payment_method", table_name="invoices")
    op.drop_column("invoices", "paid_at")
    op.drop_column("invoices", "processing_fee")
    op.drop_column("invoices", "payment_method")