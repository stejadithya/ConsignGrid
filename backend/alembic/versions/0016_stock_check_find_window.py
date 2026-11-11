"""Stock check find window (release 1.11, D3): re-check and dispute details, re-count link, staff phone numbers.

Additive: nullable columns. The new statuses (RECHECK_REQUESTED, DISPUTED, SUPERSEDED) fit the existing non-native
stocktake_status enum (String(20)), so no type change is needed.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

COLUMNS = (
    ("recheck_requested_at", sa.DateTime(timezone=True)),
    ("recheck_requested_by_user_id", sa.Integer()),
    ("recheck_note", sa.Text()),
    ("disputed_at", sa.DateTime(timezone=True)),
    ("disputed_by_user_id", sa.Integer()),
    ("dispute_note", sa.Text()),
    ("recount_of_id", sa.Integer()),
)
FKS = (("recheck_requested_by_user_id", "users"), ("disputed_by_user_id", "users"), ("recount_of_id", "stocktakes"))


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("stocktakes", sa.Column(name, type_, nullable=True))
    for col, table in FKS:
        op.create_foreign_key(op.f(f"fk_stocktakes_{col}_{table}"), "stocktakes", table, [col], ["id"])
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone")
    for col, table in reversed(FKS):
        op.drop_constraint(op.f(f"fk_stocktakes_{col}_{table}"), "stocktakes", type_="foreignkey")
    for name, _ in reversed(COLUMNS):
        op.drop_column("stocktakes", name)
