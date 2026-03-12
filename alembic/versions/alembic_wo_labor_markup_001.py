from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# Revision identifiers, used by Alembic.
revision = "wo_labor_markup_001"
down_revision = "be5161a267ac"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    tables = inspector.get_table_names()

    # 1) Crear work_order_labors solo si no existe
    if "work_order_labors" not in tables:
        op.create_table(
            "work_order_labors",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("work_order_id", sa.Integer(), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("hours", sa.Numeric(12, 2), nullable=False, server_default="1.00"),
            sa.Column("rate", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        )

    # 2) Agregar cost_snapshot a work_order_items solo si no existe
    columns = [col["name"] for col in inspector.get_columns("work_order_items")]
    if "cost_snapshot" not in columns:
        op.add_column(
            "work_order_items",
            sa.Column("cost_snapshot", sa.Numeric(12, 2), nullable=False, server_default="0")
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = [col["name"] for col in inspector.get_columns("work_order_items")]
    if "cost_snapshot" in columns:
        op.drop_column("work_order_items", "cost_snapshot")

    tables = inspector.get_table_names()
    if "work_order_labors" in tables:
        op.drop_table("work_order_labors")