""""Get this tyre for me": a stock request line the warehouse arranges from another dealer.

Additive: three columns on stock_request_lines (existing rows get find_for_me=false, qty_arranging=0) and the
within-requested check now also counts the quantity being arranged (0 for every existing row).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stock_request_lines', sa.Column('find_for_me', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('stock_request_lines', sa.Column('qty_arranging', sa.Integer(), server_default='0', nullable=False))
    op.add_column('stock_request_lines', sa.Column('arranging_transfer_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_stock_request_lines_arranging_transfer_id_transfers'), 'stock_request_lines',
                          'transfers', ['arranging_transfer_id'], ['id'])
    op.drop_constraint(op.f('ck_stock_request_lines_within_requested'), 'stock_request_lines', type_='check')
    op.create_check_constraint(op.f('ck_stock_request_lines_within_requested'), 'stock_request_lines',
                               'qty_approved + qty_rejected + qty_backordered + qty_arranging <= qty_requested')
    op.create_check_constraint(op.f('ck_stock_request_lines_arranging_non_negative'), 'stock_request_lines',
                               'qty_arranging >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_stock_request_lines_arranging_non_negative'), 'stock_request_lines', type_='check')
    op.drop_constraint(op.f('ck_stock_request_lines_within_requested'), 'stock_request_lines', type_='check')
    op.create_check_constraint(op.f('ck_stock_request_lines_within_requested'), 'stock_request_lines',
                               'qty_approved + qty_rejected + qty_backordered <= qty_requested')
    op.drop_constraint(op.f('fk_stock_request_lines_arranging_transfer_id_transfers'), 'stock_request_lines',
                       type_='foreignkey')
    op.drop_column('stock_request_lines', 'arranging_transfer_id')
    op.drop_column('stock_request_lines', 'qty_arranging')
    op.drop_column('stock_request_lines', 'find_for_me')
