"""Website stock API keys (Stage A): keys the customer website's server uses to read warehouse stock status.

Additive: one new table. Only a SHA-256 hash of each key is stored.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_partner_api_keys_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], name=op.f("fk_partner_api_keys_revoked_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_partner_api_keys_key_hash")),
    )


def downgrade() -> None:
    op.drop_table("partner_api_keys")
