"""create turmas e matriculas (com lista de espera)

Revision ID: 193453ca12ea
Revises: 62959ecab341
Create Date: 2026-11-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '193453ca12ea'
down_revision: Union[str, Sequence[str], None] = '62959ecab341'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-51 · US-04: CHECK instead of a Postgres ENUM, as in the other Gestão tables.
SITUACOES_MATRICULA = ("ativa", "espera", "desligada")


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


def upgrade() -> None:
    """Upgrade schema."""
    # A class of a program: where (a space of the same program), who leads it (a user with
    # an active team link, checked by the API because the link may end later) and when.
    # The schedule is structured (weekdays + start/end time) so overlapping classes can be
    # detected; weekdays use ISO numbers, 1 = Monday ... 7 = Sunday.
    op.create_table(
        "turmas",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("programa_id", "projetos.id", "turmas", nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        _fk("espaco_id", "espacos.id", "turmas", nullable=False),
        _fk("responsavel_id", "usuarios.id", "turmas", nullable=False),
        sa.Column("capacidade", sa.Integer(), nullable=False),
        sa.Column("dias_semana", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        _fk("criado_por", "usuarios.id", "turmas", nullable=True),
        _criado_em(),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_turmas_nome_preenchido"),
        sa.CheckConstraint("capacidade > 0", name="ck_turmas_capacidade_positiva"),
        sa.CheckConstraint("hora_fim > hora_inicio", name="ck_turmas_hora_fim_depois_do_inicio"),
        sa.CheckConstraint(
            "cardinality(dias_semana) > 0 AND dias_semana <@ ARRAY[1,2,3,4,5,6,7]::smallint[]",
            name="ck_turmas_dias_semana_validos",
        ),
    )
    op.create_index(
        "ux_turmas_programa_id_nome", "turmas", ["programa_id", sa.text("lower(nome)")], unique=True
    )

    # Enrollments and the waiting list in one table: a person waits ("espera") until a
    # place opens, is active ("ativa") while enrolled and leaves ("desligada") with date and
    # reason. Rows are never deleted, so the history stays. The waiting order is inscrito_em.
    op.create_table(
        "matriculas",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("turma_id", "turmas.id", "matriculas", nullable=False),
        _fk("pessoa_id", "pessoas.id", "matriculas", nullable=False),
        sa.Column("situacao", sa.String(), nullable=False),
        sa.Column(
            "inscrito_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Filled when the person takes a place (straight away or called from the waiting list).
        sa.Column("data_entrada", sa.Date(), nullable=True),
        sa.Column("data_saida", sa.Date(), nullable=True),
        sa.Column("motivo_saida", sa.Text(), nullable=True),
        _fk("criado_por", "usuarios.id", "matriculas", nullable=True),
        _criado_em(),
        sa.CheckConstraint(
            "situacao IN (" + ", ".join(f"'{s}'" for s in SITUACOES_MATRICULA) + ")",
            name="ck_matriculas_situacao_valida",
        ),
        # US-04: leaving requires date and reason.
        sa.CheckConstraint(
            "situacao <> 'desligada' OR (data_saida IS NOT NULL AND length(btrim(coalesce(motivo_saida, ''))) > 0)",
            name="ck_matriculas_desligamento_com_data_e_motivo",
        ),
        sa.CheckConstraint(
            "situacao <> 'ativa' OR data_entrada IS NOT NULL", name="ck_matriculas_ativa_com_entrada"
        ),
        sa.CheckConstraint(
            "data_saida IS NULL OR data_entrada IS NULL OR data_saida >= data_entrada",
            name="ck_matriculas_saida_depois_da_entrada",
        ),
    )
    # One open enrollment (active or waiting) per person and class; leaving and coming back
    # creates a new row.
    op.create_index(
        "ux_matriculas_em_aberto",
        "matriculas",
        ["turma_id", "pessoa_id"],
        unique=True,
        postgresql_where=sa.text("situacao <> 'desligada'"),
    )
    op.create_index("ix_matriculas_turma_situacao", "matriculas", ["turma_id", "situacao", "inscrito_em"])
    op.create_index("ix_matriculas_pessoa_id", "matriculas", ["pessoa_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("matriculas")
    op.drop_table("turmas")
