"""Pilot: four business roles, forced password change flag, pilot feedback.

Role mapping for existing rows (no data is deleted here; use scripts/reset_to_pilot.py for a clean start):
  DEALERSHIP_MANAGER -> RELATIONSHIP_MANAGER
  WAREHOUSE_OPERATOR -> WAREHOUSE_MANAGER
  SYSTEM_ADMIN       -> WAREHOUSE_MANAGER     (deactivated: the old role no longer exists)
  FINANCE            -> RELATIONSHIP_MANAGER  (deactivated: the old role no longer exists)

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False))
    op.execute("UPDATE users SET role = 'RELATIONSHIP_MANAGER' WHERE role = 'DEALERSHIP_MANAGER'")
    op.execute("UPDATE users SET role = 'WAREHOUSE_MANAGER' WHERE role = 'WAREHOUSE_OPERATOR'")
    op.execute("UPDATE users SET role = 'WAREHOUSE_MANAGER', is_active = false WHERE role = 'SYSTEM_ADMIN'")
    op.execute("UPDATE users SET role = 'RELATIONSHIP_MANAGER', is_active = false WHERE role = 'FINANCE'")

    op.create_table(
        "pilot_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("page", sa.String(length=200), nullable=False),
        sa.Column("feedback_type", sa.Enum("ISSUE", "IMPROVEMENT", "QUESTION", "OTHER", name="feedback_type",
                                           native_enum=False, length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_pilot_feedback_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pilot_feedback")),
    )
    op.create_index(op.f("ix_pilot_feedback_user_id"), "pilot_feedback", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pilot_feedback_user_id"), table_name="pilot_feedback")
    op.drop_table("pilot_feedback")
    op.execute("UPDATE users SET role = 'DEALERSHIP_MANAGER' WHERE role = 'RELATIONSHIP_MANAGER'")
    op.execute("UPDATE users SET role = 'WAREHOUSE_OPERATOR' WHERE role = 'WAREHOUSE_MANAGER'")
    op.drop_column("users", "must_change_password")
