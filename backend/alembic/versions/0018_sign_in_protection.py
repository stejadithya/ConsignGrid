"""Sign-in protection (UAT round 2): lock after repeated wrong passwords, and recent-password history.

Additive: two columns on users (with defaults, so existing accounts are unaffected) and one new table.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "user_password_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_password_history_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_password_history")),
    )
    op.create_index(op.f("ix_user_password_history_user_id"), "user_password_history", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_user_password_history_user_id"), table_name="user_password_history")
    op.drop_table("user_password_history")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
