"""Invoice records completed in Xero (release 1.11): who recorded the Xero number, and when.

The Xero number itself is stored in the existing invoices.external_reference column. Additive: two nullable columns.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("xero_recorded_by_user_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("xero_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_invoices_xero_recorded_by_user_id_users"), "invoices", "users",
                          ["xero_recorded_by_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_invoices_xero_recorded_by_user_id_users"), "invoices", type_="foreignkey")
    op.drop_column("invoices", "xero_recorded_at")
    op.drop_column("invoices", "xero_recorded_by_user_id")
