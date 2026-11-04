"""add status to projetos

Revision ID: a3c5e7f9b1d2
Revises: 768d1bb2ccf2
Create Date: 2026-11-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c5e7f9b1d2'
down_revision: Union[str, Sequence[str], None] = '768d1bb2ccf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # T-29 · US-07: active/closed filter on the board dashboard.
    # server_default backfills existing rows, so old projects start as active.
    op.add_column(
        "projetos",
        sa.Column("status", sa.String(), nullable=False, server_default="ativo"),
    )
    op.create_check_constraint(
        "ck_projetos_status",
        "projetos",
        "status IN ('ativo', 'encerrado')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_projetos_status", "projetos", type_="check")
    op.drop_column("projetos", "status")
