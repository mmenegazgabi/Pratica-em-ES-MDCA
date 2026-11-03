"""create orcamento_categorias table

Revision ID: 33f66eff68ef
Revises: 14749dd94ab3
Create Date: 2026-10-27 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33f66eff68ef'
down_revision: Union[str, Sequence[str], None] = '14749dd94ab3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # US-01: budgeted amount per category. orcamentos.categorias keeps the
    # list of names; a category without a row here has no limit. The rule
    # "sum of categories <= valor_total" needs other rows, so it stays in
    # the API instead of a CHECK.
    op.create_table(
        "orcamento_categorias",
        sa.Column(
            "orcamento_id",
            sa.String(),
            sa.ForeignKey(
                "orcamentos.id",
                name="fk_orcamento_categorias_orcamento_id_orcamentos",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("valor_orcado", sa.Numeric(14, 2), nullable=False),
        sa.PrimaryKeyConstraint(
            "orcamento_id", "nome", name="pk_orcamento_categorias"
        ),
        sa.CheckConstraint(
            "valor_orcado >= 0", name="ck_orcamento_categorias_valor_nao_negativo"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Dropping the table also drops its PK, FK and CHECK constraints.
    op.drop_table("orcamento_categorias")
