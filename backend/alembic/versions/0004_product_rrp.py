"""Products: recommended retail price (RRP) for the Excel product master.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("rrp", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(op.f("ck_products_rrp_non_negative"), "products", "rrp IS NULL OR rrp >= 0")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_products_rrp_non_negative"), "products", type_="check")
    op.drop_column("products", "rrp")
