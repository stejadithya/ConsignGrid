"""Transfer route (UAT round 2): direct to the dealer, or via the warehouse where the tyres are received and checked.

Additive: four nullable columns on transfers. Existing transfers have no route and go direct, as before.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transfers", sa.Column("route", sa.String(length=20), nullable=True))
    op.add_column("transfers", sa.Column("warehouse_received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transfers", sa.Column("warehouse_received_by_user_id", sa.Integer(), nullable=True))
    op.add_column("transfers", sa.Column("warehouse_check_notes", sa.Text(), nullable=True))
    op.create_foreign_key(op.f("fk_transfers_warehouse_received_by_user_id_users"), "transfers", "users",
                          ["warehouse_received_by_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_transfers_warehouse_received_by_user_id_users"), "transfers", type_="foreignkey")
    op.drop_column("transfers", "warehouse_check_notes")
    op.drop_column("transfers", "warehouse_received_by_user_id")
    op.drop_column("transfers", "warehouse_received_at")
    op.drop_column("transfers", "route")
