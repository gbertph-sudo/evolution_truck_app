"""add quote lifecycle fields

Revision ID: quotes_lifecycle_001
Revises: wo_labor_markup_001
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "quotes_lifecycle_001"
down_revision = "wo_labor_markup_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("document_type", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("settlement_type", sa.String(length=30), nullable=True))
    op.add_column("invoices", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("invoices", sa.Column("converted_at", sa.DateTime(), nullable=True))
    op.add_column("invoices", sa.Column("inventory_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("invoices", sa.Column("quote_origin", sa.String(length=30), nullable=True))

    op.create_index("ix_invoices_document_type", "invoices", ["document_type"], unique=False)
    op.create_index("ix_invoices_settlement_type", "invoices", ["settlement_type"], unique=False)
    op.create_index("ix_invoices_expires_at", "invoices", ["expires_at"], unique=False)
    op.create_index("ix_invoices_quote_origin", "invoices", ["quote_origin"], unique=False)

    op.execute("UPDATE invoices SET document_type = 'SALE' WHERE document_type IS NULL")
    op.execute("UPDATE invoices SET inventory_applied = false WHERE inventory_applied IS NULL")


def downgrade():
    op.drop_index("ix_invoices_quote_origin", table_name="invoices")
    op.drop_index("ix_invoices_expires_at", table_name="invoices")
    op.drop_index("ix_invoices_settlement_type", table_name="invoices")
    op.drop_index("ix_invoices_document_type", table_name="invoices")

    op.drop_column("invoices", "quote_origin")
    op.drop_column("invoices", "inventory_applied")
    op.drop_column("invoices", "converted_at")
    op.drop_column("invoices", "expires_at")
    op.drop_column("invoices", "settlement_type")
    op.drop_column("invoices", "document_type")