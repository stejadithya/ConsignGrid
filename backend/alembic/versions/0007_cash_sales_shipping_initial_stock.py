"""Cash sales (customer on sale, cash account flag), shipping method and delivery-note email status on deliveries,
and the "Latest stock" flag on replenishment requests.

Additive only: no existing rows are changed.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('consignment_sales', sa.Column('customer_name', sa.String(length=200), nullable=True))
    op.add_column('consignment_sales', sa.Column('customer_phone', sa.String(length=50), nullable=True))
    op.add_column('deliveries', sa.Column('shipping_method', sa.String(length=20), server_default='COURIER', nullable=False))
    op.add_column('deliveries', sa.Column('carried_by_user_id', sa.Integer(), nullable=True))
    op.add_column('deliveries', sa.Column('note_emailed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deliveries', sa.Column('note_email_to', sa.String(length=255), nullable=True))
    op.add_column('deliveries', sa.Column('note_email_error', sa.Text(), nullable=True))
    op.create_foreign_key(op.f('fk_deliveries_carried_by_user_id_users'), 'deliveries', 'users', ['carried_by_user_id'], ['id'])
    op.add_column('replenishment_requests', sa.Column('first_supply', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('resellers', sa.Column('is_cash_account', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('resellers', 'is_cash_account')
    op.drop_column('replenishment_requests', 'first_supply')
    op.drop_constraint(op.f('fk_deliveries_carried_by_user_id_users'), 'deliveries', type_='foreignkey')
    op.drop_column('deliveries', 'note_email_error')
    op.drop_column('deliveries', 'note_email_to')
    op.drop_column('deliveries', 'note_emailed_at')
    op.drop_column('deliveries', 'carried_by_user_id')
    op.drop_column('deliveries', 'shipping_method')
    op.drop_column('consignment_sales', 'customer_phone')
    op.drop_column('consignment_sales', 'customer_name')
