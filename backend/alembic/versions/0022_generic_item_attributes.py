"""Generic items (white-label step 1.4): pack-defined attributes on products; tyre columns become optional.

Additive: one new JSONB column with a GIN index. The five tyre columns become nullable so that non-tyre Industry
Packs can store items without a tyre size; the tyres pack still requires them (validated by the application), and a
check constraint keeps the size either complete or absent. Existing rows are unchanged.

Downgrade restores NOT NULL, which is only possible while every product still has a tyre size.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

TYRE_COLUMNS = (("width", sa.Integer()), ("aspect_ratio", sa.Integer()), ("rim_diameter", sa.Numeric(4, 1)),
                ("load_index", sa.String(10)), ("speed_rating", sa.String(3)))


def upgrade() -> None:
    op.add_column("products", sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                                        server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_products_attributes", "products", ["attributes"], postgresql_using="gin")
    for name, type_ in TYRE_COLUMNS:
        op.alter_column("products", name, existing_type=type_, nullable=True)
    op.drop_constraint(op.f("ck_products_positive_dimensions"), "products", type_="check")
    op.create_check_constraint(
        "positive_dimensions", "products",
        "(width IS NULL OR width > 0) AND (aspect_ratio IS NULL OR aspect_ratio > 0) "
        "AND (rim_diameter IS NULL OR rim_diameter > 0)")
    op.create_check_constraint(
        "tyre_size_complete", "products",
        "(width IS NULL) = (aspect_ratio IS NULL) AND (width IS NULL) = (rim_diameter IS NULL)")


def downgrade() -> None:
    bind = op.get_bind()
    missing = bind.execute(sa.text("SELECT count(*) FROM products WHERE width IS NULL OR load_index IS NULL "
                                   "OR speed_rating IS NULL")).scalar_one()
    if missing:
        raise RuntimeError(f"{missing} product(s) have no tyre size; they must be removed or completed before "
                           "downgrading below 0022")
    op.drop_constraint(op.f("ck_products_tyre_size_complete"), "products", type_="check")
    op.drop_constraint(op.f("ck_products_positive_dimensions"), "products", type_="check")
    op.create_check_constraint("positive_dimensions", "products",
                               "width > 0 AND aspect_ratio > 0 AND rim_diameter > 0")
    for name, type_ in TYRE_COLUMNS:
        op.alter_column("products", name, existing_type=type_, nullable=False)
    op.drop_index("ix_products_attributes", table_name="products")
    op.drop_column("products", "attributes")
