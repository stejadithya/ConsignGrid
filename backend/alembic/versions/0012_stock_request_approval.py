"""Stock request approval (release 1.11): approval details, escalation to a Relationship Manager.

Additive: new nullable columns on stock_requests; existing requests are unaffected.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_requests", sa.Column("approval_method", sa.String(length=20), nullable=True))
    op.add_column("stock_requests", sa.Column("approval_contact", sa.String(length=200), nullable=True))
    op.add_column("stock_requests", sa.Column("approval_comments", sa.Text(), nullable=True))
    op.add_column("stock_requests", sa.Column("escalated_to_user_id", sa.Integer(), nullable=True))
    op.add_column("stock_requests", sa.Column("escalated_by_user_id", sa.Integer(), nullable=True))
    op.add_column("stock_requests", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_requests", sa.Column("escalation_note", sa.Text(), nullable=True))
    op.create_foreign_key(op.f("fk_stock_requests_escalated_to_user_id_users"), "stock_requests", "users",
                          ["escalated_to_user_id"], ["id"])
    op.create_foreign_key(op.f("fk_stock_requests_escalated_by_user_id_users"), "stock_requests", "users",
                          ["escalated_by_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(op.f("fk_stock_requests_escalated_by_user_id_users"), "stock_requests", type_="foreignkey")
    op.drop_constraint(op.f("fk_stock_requests_escalated_to_user_id_users"), "stock_requests", type_="foreignkey")
    op.drop_column("stock_requests", "escalation_note")
    op.drop_column("stock_requests", "escalated_at")
    op.drop_column("stock_requests", "escalated_by_user_id")
    op.drop_column("stock_requests", "escalated_to_user_id")
    op.drop_column("stock_requests", "approval_comments")
    op.drop_column("stock_requests", "approval_contact")
    op.drop_column("stock_requests", "approval_method")
