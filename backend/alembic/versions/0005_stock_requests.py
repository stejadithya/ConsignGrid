"""Consignment stock requests (multi-SKU, approval stage), their history, in-app notifications,
and shipment / delivery details on deliveries (tracking number, address, delivery reference).

Additive only: no existing rows are changed.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)
    op.create_table('stock_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=20), nullable=False),
    sa.Column('reseller_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'PARTIALLY_APPROVED', 'REJECTED', 'READY_FOR_SHIPMENT', 'SHIPPED', 'DELIVERED', 'CANCELLED', name='stock_request_status', native_enum=False, length=30), nullable=False),
    sa.Column('decision', sa.Enum('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'PARTIALLY_APPROVED', 'REJECTED', 'READY_FOR_SHIPMENT', 'SHIPPED', 'DELIVERED', 'CANCELLED', name='stock_request_status', native_enum=False, length=30), nullable=True),
    sa.Column('priority', sa.Enum('URGENT', 'HIGH', 'NORMAL', 'LOW', name='priority', native_enum=False, length=10), nullable=False),
    sa.Column('required_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('shipping_address', sa.Text(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=False),
    sa.Column('created_by_role', sa.String(length=30), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('reviewed_by_role', sa.String(length=30), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_stock_requests_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_stock_requests_location_id_locations')),
    sa.ForeignKeyConstraint(['reseller_id'], ['resellers.id'], name=op.f('fk_stock_requests_reseller_id_resellers')),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fk_stock_requests_reviewed_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_requests')),
    sa.UniqueConstraint('number', name=op.f('uq_stock_requests_number'))
    )
    op.create_index(op.f('ix_stock_requests_created_by_user_id'), 'stock_requests', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_stock_requests_reseller_id'), 'stock_requests', ['reseller_id'], unique=False)
    op.create_index(op.f('ix_stock_requests_status'), 'stock_requests', ['status'], unique=False)
    op.create_table('stock_request_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stock_request_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('from_status', sa.String(length=30), nullable=True),
    sa.Column('to_status', sa.String(length=30), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('actor_role', sa.String(length=30), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_stock_request_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['stock_request_id'], ['stock_requests.id'], name=op.f('fk_stock_request_events_stock_request_id_stock_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_request_events'))
    )
    op.create_index('ix_stock_request_events_request', 'stock_request_events', ['stock_request_id', 'id'], unique=False)
    op.create_table('stock_request_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stock_request_id', sa.Integer(), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('qty_requested', sa.Integer(), nullable=False),
    sa.Column('qty_approved', sa.Integer(), nullable=False),
    sa.Column('qty_rejected', sa.Integer(), nullable=False),
    sa.Column('qty_backordered', sa.Integer(), nullable=False),
    sa.Column('qty_released', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('decision_notes', sa.Text(), nullable=True),
    sa.Column('replenishment_request_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('qty_approved + qty_rejected + qty_backordered <= qty_requested', name=op.f('ck_stock_request_lines_within_requested')),
    sa.CheckConstraint('qty_approved >= 0 AND qty_rejected >= 0 AND qty_backordered >= 0 AND qty_released >= 0', name=op.f('ck_stock_request_lines_non_negative')),
    sa.CheckConstraint('qty_released <= qty_approved', name=op.f('ck_stock_request_lines_released_within_approved')),
    sa.CheckConstraint('qty_requested > 0', name=op.f('ck_stock_request_lines_requested_positive')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_stock_request_lines_product_id_products')),
    sa.ForeignKeyConstraint(['replenishment_request_id'], ['replenishment_requests.id'], name=op.f('fk_stock_request_lines_replenishment_request_id_replenishment_requests')),
    sa.ForeignKeyConstraint(['stock_request_id'], ['stock_requests.id'], name=op.f('fk_stock_request_lines_stock_request_id_stock_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_request_lines')),
    sa.UniqueConstraint('replenishment_request_id', name=op.f('uq_stock_request_lines_replenishment_request_id')),
    sa.UniqueConstraint('stock_request_id', 'product_id', name='one_line_per_product')
    )
    op.create_index(op.f('ix_stock_request_lines_product_id'), 'stock_request_lines', ['product_id'], unique=False)
    op.create_index(op.f('ix_stock_request_lines_stock_request_id'), 'stock_request_lines', ['stock_request_id'], unique=False)
    op.add_column('deliveries', sa.Column('tracking_number', sa.String(length=100), nullable=True))
    op.add_column('deliveries', sa.Column('shipping_address', sa.Text(), nullable=True))
    op.add_column('deliveries', sa.Column('stock_request_id', sa.Integer(), nullable=True))
    op.add_column('deliveries', sa.Column('delivered_on', sa.Date(), nullable=True))
    op.add_column('deliveries', sa.Column('delivery_reference', sa.String(length=100), nullable=True))
    op.add_column('deliveries', sa.Column('receipt_notes', sa.Text(), nullable=True))
    op.create_index(op.f('ix_deliveries_stock_request_id'), 'deliveries', ['stock_request_id'], unique=False)
    op.create_foreign_key(op.f('fk_deliveries_stock_request_id_stock_requests'), 'deliveries', 'stock_requests', ['stock_request_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_deliveries_stock_request_id_stock_requests'), 'deliveries', type_='foreignkey')
    op.drop_index(op.f('ix_deliveries_stock_request_id'), table_name='deliveries')
    op.drop_column('deliveries', 'receipt_notes')
    op.drop_column('deliveries', 'delivery_reference')
    op.drop_column('deliveries', 'delivered_on')
    op.drop_column('deliveries', 'stock_request_id')
    op.drop_column('deliveries', 'shipping_address')
    op.drop_column('deliveries', 'tracking_number')
    op.drop_index(op.f('ix_stock_request_lines_stock_request_id'), table_name='stock_request_lines')
    op.drop_index(op.f('ix_stock_request_lines_product_id'), table_name='stock_request_lines')
    op.drop_table('stock_request_lines')
    op.drop_index('ix_stock_request_events_request', table_name='stock_request_events')
    op.drop_table('stock_request_events')
    op.drop_index(op.f('ix_stock_requests_status'), table_name='stock_requests')
    op.drop_index(op.f('ix_stock_requests_reseller_id'), table_name='stock_requests')
    op.drop_index(op.f('ix_stock_requests_created_by_user_id'), table_name='stock_requests')
    op.drop_table('stock_requests')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
