"""add conciliacao fields to lancamentos

Revision ID: 768d1bb2ccf2
Revises: 33f66eff68ef
Create Date: 2026-10-27 18:30:47.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '768d1bb2ccf2'
down_revision: Union[str, Sequence[str], None] = '33f66eff68ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # T-20 · US-05: manual bank reconciliation.
    # server_default backfills existing rows, so old entries start as not reconciled.
    op.add_column(
        "lancamentos",
        sa.Column("conciliado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Nullable: only set once the entry is matched to a bank statement item.
    op.add_column(
        "lancamentos",
        sa.Column("item_extrato_ref", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("lancamentos", "item_extrato_ref")
    op.drop_column("lancamentos", "conciliado")
