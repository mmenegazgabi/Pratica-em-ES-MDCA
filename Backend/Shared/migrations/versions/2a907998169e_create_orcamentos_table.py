"""create orcamentos table

Revision ID: 2a907998169e
Revises: 149f842c4ee5
Create Date: 2026-09-29 19:15:59.287368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2a907998169e'
down_revision: Union[str, Sequence[str], None] = '149f842c4ee5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "orcamentos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "projeto_id",
            sa.String(),
            sa.ForeignKey("projetos.id"),
            nullable=False,
        ),
        sa.Column("valor_total", sa.Numeric(), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("categorias_despesa", postgresql.ARRAY(sa.String()), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("orcamentos")
