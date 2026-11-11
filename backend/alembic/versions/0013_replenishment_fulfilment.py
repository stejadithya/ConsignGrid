"""Replenishment fulfilment (release 1.11): approval details, escalation to a Relationship Manager, ready to ship.

Additive: new nullable columns on replenishment_requests; existing requests are unaffected.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

USER_FKS = ("approved_by_user_id", "escalated_to_user_id", "escalated_by_user_id", "ready_by_user_id")


def upgrade() -> None:
    op.add_column("replenishment_requests", sa.Column("approval_method", sa.String(length=20), nullable=True))
    op.add_column("replenishment_requests", sa.Column("approval_contact", sa.String(length=200), nullable=True))
    op.add_column("replenishment_requests", sa.Column("approval_comments", sa.Text(), nullable=True))
    op.add_column("replenishment_requests", sa.Column("approved_by_user_id", sa.Integer(), nullable=True))
    op.add_column("replenishment_requests", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("replenishment_requests", sa.Column("escalated_to_user_id", sa.Integer(), nullable=True))
    op.add_column("replenishment_requests", sa.Column("escalated_by_user_id", sa.Integer(), nullable=True))
    op.add_column("replenishment_requests", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("replenishment_requests", sa.Column("escalation_note", sa.Text(), nullable=True))
    op.add_column("replenishment_requests", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("replenishment_requests", sa.Column("ready_by_user_id", sa.Integer(), nullable=True))
    for col in USER_FKS:
        op.create_foreign_key(op.f(f"fk_replenishment_requests_{col}_users"), "replenishment_requests", "users",
                              [col], ["id"])


def downgrade() -> None:
    for col in reversed(USER_FKS):
        op.drop_constraint(op.f(f"fk_replenishment_requests_{col}_users"), "replenishment_requests",
                           type_="foreignkey")
    for col in ("ready_by_user_id", "ready_at", "escalation_note", "escalated_at", "escalated_by_user_id",
                "escalated_to_user_id", "approved_at", "approved_by_user_id", "approval_comments",
                "approval_contact", "approval_method"):
        op.drop_column("replenishment_requests", col)
