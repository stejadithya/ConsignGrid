"""Dealer onboarding (release 1.11): copies of signed consignment agreements.

Additive: a new table. Account references and shop codes need no schema change (they use number_sequences and the
existing columns); existing dealers keep their references and codes.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consignment_agreement_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reseller_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 5242880", name=op.f("ck_consignment_agreement_files_agreement_file_size")),
        sa.CheckConstraint("content_type IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')",
                           name=op.f("ck_consignment_agreement_files_agreement_file_type")),
        sa.ForeignKeyConstraint(["reseller_id"], ["resellers.id"], name=op.f("fk_consignment_agreement_files_reseller_id_resellers")),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"],
                                name=op.f("fk_consignment_agreement_files_uploaded_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consignment_agreement_files")),
    )
    op.create_index(op.f("ix_consignment_agreement_files_reseller_id"), "consignment_agreement_files", ["reseller_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_consignment_agreement_files_reseller_id"), table_name="consignment_agreement_files")
    op.drop_table("consignment_agreement_files")
