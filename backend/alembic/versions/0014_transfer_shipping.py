"""Transfer shipping (release 1.11): a sales rep or courier carries the tyres; transfer delivery note email.

Additive: new nullable columns on transfers; existing transfers keep today's rules.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

USER_FKS = ("carried_by_user_id", "shipping_arranged_by_user_id")
COLUMNS = (
    ("shipping_method", sa.String(length=20)),
    ("carrier_reference", sa.String(length=100)),
    ("tracking_number", sa.String(length=100)),
    ("carried_by_user_id", sa.Integer()),
    ("shipping_arranged_at", sa.DateTime(timezone=True)),
    ("shipping_arranged_by_user_id", sa.Integer()),
    ("collected_from_name", sa.String(length=120)),
    ("note_emailed_at", sa.DateTime(timezone=True)),
    ("note_email_to", sa.String(length=255)),
    ("note_email_error", sa.Text()),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("transfers", sa.Column(name, type_, nullable=True))
    for col in USER_FKS:
        op.create_foreign_key(op.f(f"fk_transfers_{col}_users"), "transfers", "users", [col], ["id"])


def downgrade() -> None:
    for col in reversed(USER_FKS):
        op.drop_constraint(op.f(f"fk_transfers_{col}_users"), "transfers", type_="foreignkey")
    for name, _ in reversed(COLUMNS):
        op.drop_column("transfers", name)
