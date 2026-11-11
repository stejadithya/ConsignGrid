"""Stock checks: reseller confirmation of shortages (due time, reminders, held quantity, draft invoice link).

Additive only: no existing rows are changed.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stocktake_lines', sa.Column('qty_held', sa.Integer(), server_default='0', nullable=False))
    op.add_column('stocktakes', sa.Column('confirm_due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('stocktakes', sa.Column('last_reminded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('stocktakes', sa.Column('reminder_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('stocktakes', sa.Column('confirmed_on_behalf_reason', sa.Text(), nullable=True))
    op.add_column('stocktakes', sa.Column('invoice_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_stocktakes_confirm_due_at'), 'stocktakes', ['confirm_due_at'], unique=False)
    op.create_foreign_key(op.f('fk_stocktakes_invoice_id_invoices'), 'stocktakes', 'invoices', ['invoice_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_stocktakes_invoice_id_invoices'), 'stocktakes', type_='foreignkey')
    op.drop_index(op.f('ix_stocktakes_confirm_due_at'), table_name='stocktakes')
    op.drop_column('stocktakes', 'invoice_id')
    op.drop_column('stocktakes', 'confirmed_on_behalf_reason')
    op.drop_column('stocktakes', 'reminder_count')
    op.drop_column('stocktakes', 'last_reminded_at')
    op.drop_column('stocktakes', 'confirm_due_at')
    op.drop_column('stocktake_lines', 'qty_held')
