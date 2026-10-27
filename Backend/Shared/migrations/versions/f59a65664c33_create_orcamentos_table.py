"""create orcamentos table

Revision ID: f59a65664c33
Revises: 4113860459ea
Create Date: 2026-10-27 17:47:49.973746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f59a65664c33'
down_revision: Union[str, Sequence[str], None] = '4113860459ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "orcamentos",
        sa.Column("id", sa.String(), primary_key=True),
        # String to match projetos.id and the projeto_id used by the API.
        sa.Column(
            "projeto_id",
            sa.String(),
            sa.ForeignKey("projetos.id", name="fk_orcamentos_projeto_id_projetos"),
            nullable=False,
        ),
        sa.Column("valor_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("categorias", postgresql.ARRAY(sa.Text()), nullable=False),
    )
    op.create_index("ix_orcamentos_projeto_id", "orcamentos", ["projeto_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_orcamentos_projeto_id", table_name="orcamentos")
    op.drop_table("orcamentos")
