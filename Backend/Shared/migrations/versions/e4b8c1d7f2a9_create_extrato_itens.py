"""extrato bancário (US-05): tabela extrato_itens

Os itens do extrato importado (POST /extrato) passam a ficar no banco junto com os
lançamentos, em vez da memória do processo. ``conciliado_com`` é o lançamento a que o
item foi ligado na conciliação (PATCH /lancamentos/{id}/conciliar): no máximo um item
por lançamento (índice único parcial) e um lançamento por item (a própria coluna).

``ordem`` só guarda a ordem de gravação, para a lista sair, na mesma data, na ordem em
que os itens foram importados.

Só adiciona uma tabela: o código que já está no ar continua funcionando.

Revision ID: e4b8c1d7f2a9
Revises: e4a6c8b0d2f1
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b8c1d7f2a9'
down_revision: Union[str, Sequence[str], None] = 'e4a6c8b0d2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "extrato_itens",
        # lancamentos.id é String (varchar): mesmo tipo aqui e em conciliado_com.
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "importado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "conciliado_com",
            sa.String(),
            sa.ForeignKey(
                "lancamentos.id",
                name="fk_extrato_itens_conciliado_com_lancamentos",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("ordem", sa.BigInteger(), sa.Identity(), nullable=False),
    )
    op.create_index("ix_extrato_itens_data", "extrato_itens", ["data"])
    op.create_index(
        "uq_extrato_itens_conciliado_com",
        "extrato_itens",
        ["conciliado_com"],
        unique=True,
        postgresql_where=sa.text("conciliado_com IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_extrato_itens_conciliado_com", table_name="extrato_itens")
    op.drop_index("ix_extrato_itens_data", table_name="extrato_itens")
    op.drop_table("extrato_itens")
