"""create atividades (encontros), chamadas e evidencias

Revision ID: 4e3a59521428
Revises: 193453ca12ea
Create Date: 2026-11-09 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e3a59521428'
down_revision: Union[str, Sequence[str], None] = '193453ca12ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-55 · US-05. Created in this order, dropped in reverse.
TABELAS = ("atividades", "chamadas", "evidencias")

# Lets atividades point at (turma, programa) so a meeting can't name a class of another
# program. Created here and dropped on downgrade; turmas itself belongs to T-51.
UQ_TURMAS_ID_PROGRAMA = "uq_turmas_id_programa_id"


def _criado_em() -> sa.Column:
    return sa.Column(
        "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _fk(coluna: str, alvo: str, tabela: str, *, nullable: bool, ondelete: str = None) -> sa.Column:
    nome_alvo = alvo.split(".")[0]
    return sa.Column(
        coluna,
        sa.String(),
        sa.ForeignKey(alvo, name=f"fk_{tabela}_{coluna}_{nome_alvo}", ondelete=ondelete),
        nullable=nullable,
    )


def _registro_id() -> sa.Column:
    # Id generated on the device when the record is made (possibly offline). Sending the
    # same record again during sync hits this unique key instead of creating a copy.
    return sa.Column("registro_id", sa.String(), nullable=False, unique=True)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(UQ_TURMAS_ID_PROGRAMA, "turmas", ["id", "programa_id"])

    # A meeting of a class (encontro): the header of the attendance call. When it happened,
    # which class, which educator led it and what was worked on.
    op.create_table(
        "atividades",
        sa.Column("id", sa.String(), primary_key=True),
        _registro_id(),
        _fk("programa_id", "projetos.id", "atividades", nullable=False),
        sa.Column("turma_id", sa.String(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        _fk("educador_id", "usuarios.id", "atividades", nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        _fk("criado_por", "usuarios.id", "atividades", nullable=True),
        _criado_em(),
        sa.ForeignKeyConstraint(
            ["turma_id", "programa_id"],
            ["turmas.id", "turmas.programa_id"],
            name="fk_atividades_turma_programa_turmas",
        ),
        # Evidências point at (atividade, programa), so both must match.
        sa.UniqueConstraint("id", "programa_id", name="uq_atividades_id_programa_id"),
        sa.CheckConstraint("length(btrim(conteudo)) > 0", name="ck_atividades_conteudo_preenchido"),
    )
    op.create_index("ix_atividades_turma_data", "atividades", ["turma_id", "data"])
    op.create_index("ix_atividades_programa_data", "atividades", ["programa_id", "data"])

    # The attendance call: one row per person of the class in that meeting. Present and
    # absent people are the rows with presente true/false. Rows go with their meeting.
    op.create_table(
        "chamadas",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("atividade_id", "atividades.id", "chamadas", nullable=False, ondelete="CASCADE"),
        _fk("pessoa_id", "pessoas.id", "chamadas", nullable=False),
        sa.Column("presente", sa.Boolean(), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=True),
        _criado_em(),
        sa.UniqueConstraint("atividade_id", "pessoa_id", name="uq_chamadas_atividade_id_pessoa_id"),
        sa.CheckConstraint(
            "NOT presente OR justificativa IS NULL", name="ck_chamadas_justificativa_so_em_ausencia"
        ),
    )
    op.create_index("ix_chamadas_pessoa_id", "chamadas", ["pessoa_id"])

    # Evidence of a meeting (photo, list, PDF). The file lives in the private R2 bucket
    # (ARQ-04); the database keeps only the metadata and the object key.
    op.create_table(
        "evidencias",
        sa.Column("id", sa.String(), primary_key=True),
        _registro_id(),
        sa.Column("atividade_id", sa.String(), nullable=False),
        sa.Column("programa_id", sa.String(), nullable=False),
        _fk("autor_id", "usuarios.id", "evidencias", nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("chave_arquivo", sa.Text(), nullable=False, unique=True),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("tamanho", sa.BigInteger(), nullable=False),
        _criado_em(),
        sa.ForeignKeyConstraint(
            ["atividade_id", "programa_id"],
            ["atividades.id", "atividades.programa_id"],
            name="fk_evidencias_atividade_programa_atividades",
        ),
        sa.ForeignKeyConstraint(["programa_id"], ["projetos.id"], name="fk_evidencias_programa_id_projetos"),
        sa.CheckConstraint("length(btrim(nome_arquivo)) > 0", name="ck_evidencias_nome_arquivo_preenchido"),
        sa.CheckConstraint("chave_arquivo LIKE 'gestao/evidencias/%'", name="ck_evidencias_chave_na_pasta_da_gestao"),
        sa.CheckConstraint("tamanho > 0", name="ck_evidencias_tamanho_positivo"),
    )
    op.create_index("ix_evidencias_atividade_id", "evidencias", ["atividade_id"])
    op.create_index("ix_evidencias_programa_data", "evidencias", ["programa_id", "data"])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(TABELAS):
        op.drop_table(tabela)
    op.drop_constraint(UQ_TURMAS_ID_PROGRAMA, "turmas", type_="unique")
