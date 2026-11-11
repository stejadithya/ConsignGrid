"""How a dealer joined (UAT round 2): already holding TyreGrow stock, or new (stock comes through requests).

Additive: one nullable column. Dealers added before this keep NULL and are treated as before.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resellers", sa.Column("joined_with_stock", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("resellers", "joined_with_stock")
