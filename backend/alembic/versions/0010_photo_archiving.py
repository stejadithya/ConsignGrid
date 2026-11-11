"""Drop-off photo archiving: archived / deleted timestamps on photos and a small app settings table.

Additive: existing photos stay active (archived_at and deleted_at empty). The photo data column becomes nullable
so a deleted photo keeps its record (who, when) without the image.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('proof_photos', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('proof_photos', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('proof_photos', 'data', existing_type=sa.LargeBinary(), nullable=True)
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_app_settings_updated_by_user_id_users')),
        sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings')),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
    op.execute("DELETE FROM proof_photos WHERE data IS NULL")
    op.alter_column('proof_photos', 'data', existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column('proof_photos', 'deleted_at')
    op.drop_column('proof_photos', 'archived_at')
