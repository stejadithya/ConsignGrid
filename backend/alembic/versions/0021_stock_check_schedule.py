"""Stock check schedule (UAT round 2): a shop's moved check date with the reason, and which reminders went out.

Additive: one new table. Without a row a shop is due 30 days after its last count, as before.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_check_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("next_check_on", sa.Date(), nullable=True),
        sa.Column("moved_reason", sa.Text(), nullable=True),
        sa.Column("moved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_notified_on", sa.Date(), nullable=True),
        sa.Column("overdue_notified_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name=op.f("fk_stock_check_schedules_location_id_locations")),
        sa.ForeignKeyConstraint(["moved_by_user_id"], ["users.id"], name=op.f("fk_stock_check_schedules_moved_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_check_schedules")),
        sa.UniqueConstraint("location_id", name=op.f("uq_stock_check_schedules_location_id")),
    )


def downgrade() -> None:
    op.drop_table("stock_check_schedules")
