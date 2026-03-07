from alembic import op
import sqlalchemy as sa

revision = "xxxx"
down_revision = "c54e5b7dc67b"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "users",
        sa.Column("email", sa.Text(), nullable=False, unique=True)
    )

def downgrade():
    op.drop_column("users", "email")