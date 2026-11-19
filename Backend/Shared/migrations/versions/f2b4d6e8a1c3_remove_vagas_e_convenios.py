"""remove vagas ofertadas e convênios dos programas

As tabelas ``vagas`` e ``convenios`` (criadas na 5c2e8d41a7b3, US-02) só eram
cadastradas e listadas, sem uso em turmas, indicadores, Visão integrada ou Financeiro.
As vagas ofertadas ainda competiam com a capacidade das turmas, que é o número que
controla matrícula e lista de espera. As duas saem.

O downgrade recria as tabelas vazias, como eram; os registros apagados não voltam
(há backup do banco antes de aplicar em produção).

Revision ID: f2b4d6e8a1c3
Revises: e4b8c1d7f2a9
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b4d6e8a1c3'
down_revision: Union[str, Sequence[str], None] = 'e4b8c1d7f2a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apaga as tabelas de vagas ofertadas e de convênios (índices e regras vão junto)."""
    op.drop_table("vagas")
    op.drop_table("convenios")


def _programa_fk(tabela: str) -> sa.Column:
    return sa.Column(
        "programa_id",
        sa.String(),
        sa.ForeignKey("projetos.id", name=f"fk_{tabela}_programa_id_projetos"),
        nullable=False,
    )


def downgrade() -> None:
    """Recria as duas tabelas vazias, iguais às da 5c2e8d41a7b3."""
    op.create_table(
        "convenios",
        sa.Column("id", sa.String(), primary_key=True),
        _programa_fk("convenios"),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("concedente", sa.Text(), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_convenios_nome_preenchido"),
        sa.CheckConstraint(
            "vigencia_inicio IS NULL OR vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_convenios_vigencia_fim_depois_do_inicio",
        ),
    )
    op.create_index("ix_convenios_programa_id", "convenios", ["programa_id"])
    op.create_table(
        "vagas",
        sa.Column("id", sa.String(), primary_key=True),
        _programa_fk("vagas"),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(btrim(descricao)) > 0", name="ck_vagas_descricao_preenchida"),
        sa.CheckConstraint("quantidade > 0", name="ck_vagas_quantidade_positiva"),
    )
    op.create_index(
        "ux_vagas_programa_id_descricao",
        "vagas",
        ["programa_id", sa.text("lower(descricao)")],
        unique=True,
    )
