"""Proof of receipt: who received a delivery / transfer, receipt notes on transfers, and small drop-off photos.

Additive only: new nullable columns and a new table; no existing rows are changed.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('deliveries', sa.Column('received_by_name', sa.String(length=120), nullable=True))
    op.add_column('transfers', sa.Column('received_by_name', sa.String(length=120), nullable=True))
    op.add_column('transfers', sa.Column('receipt_notes', sa.Text(), nullable=True))
    op.create_table(
        'proof_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=30), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('taken_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['taken_by_user_id'], ['users.id'], name=op.f('fk_proof_photos_taken_by_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_proof_photos')),
    )
    op.create_index('ix_proof_photos_entity', 'proof_photos', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('ix_proof_photos_entity', table_name='proof_photos')
    op.drop_table('proof_photos')
    op.drop_column('transfers', 'receipt_notes')
    op.drop_column('transfers', 'received_by_name')
    op.drop_column('deliveries', 'received_by_name')
