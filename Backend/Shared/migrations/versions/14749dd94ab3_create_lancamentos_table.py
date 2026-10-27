"""create lancamentos table

Revision ID: 14749dd94ab3
Revises: f59a65664c33
Create Date: 2026-10-27 18:02:20.447809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14749dd94ab3'
down_revision: Union[str, Sequence[str], None] = 'f59a65664c33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lancamentos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "projeto_id",
            sa.String(),
            sa.ForeignKey("projetos.id", name="fk_lancamentos_projeto_id_projetos"),
            nullable=False,
        ),
        # The budget the entry is charged against; a projeto may have several.
        sa.Column(
            "orcamento_id",
            sa.String(),
            sa.ForeignKey("orcamentos.id", name="fk_lancamentos_orcamento_id_orcamentos"),
            nullable=False,
        ),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pendente"),
        # Nullable: the receipt may be uploaded after the entry is created.
        sa.Column("comprovante_url", sa.String(), nullable=True),
        # T-16 · US-04: reason given by whoever rejected the entry.
        sa.Column("motivo_rejeicao", sa.Text(), nullable=True),
        # T-17 · US-04: who created the entry, notified of the outcome.
        sa.Column("autor_id", sa.String(), nullable=True),
        # CHECK instead of a Postgres ENUM so dropping the table leaves no type behind.
        sa.CheckConstraint(
            "status IN ('pendente', 'aprovado', 'rejeitado')",
            name="ck_lancamentos_status",
        ),
        # Mirror the domain rules so writes outside the API stay consistent.
        sa.CheckConstraint("valor > 0", name="ck_lancamentos_valor_positivo"),
        sa.CheckConstraint(
            "length(btrim(descricao)) > 0", name="ck_lancamentos_descricao_preenchida"
        ),
        sa.CheckConstraint(
            "status <> 'rejeitado' OR length(btrim(coalesce(motivo_rejeicao, ''))) > 0",
            name="ck_lancamentos_rejeicao_com_motivo",
        ),
    )
    op.create_index("ix_lancamentos_projeto_id", "lancamentos", ["projeto_id"])
    op.create_index("ix_lancamentos_orcamento_id", "lancamentos", ["orcamento_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_lancamentos_orcamento_id", table_name="lancamentos")
    op.drop_index("ix_lancamentos_projeto_id", table_name="lancamentos")
    # Dropping the table also drops its FK and CHECK constraints.
    op.drop_table("lancamentos")
